# ruff: file-ignore[print]
import argparse
import json
import math
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import psutil  # pyright: ignore[reportMissingModuleSource]
import tomllib
from h2.connection import H2Connection  # pyright: ignore[reportMissingImports]
from h2.events import DataReceived, ResponseReceived, StreamEnded  # pyright: ignore[reportMissingImports]
from websockets.sync.client import connect

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_APP = "tools.benchmarks.free_threading_app:app"
_LOOP_EXTRAS = {"rloop": "rloop", "uvloop": "uvloop", "winloop": "winloop"}


@dataclass(frozen=True)
class _Cell:
    python: str
    loop: str
    workers: int
    workload: str


class _ProcessTreeSampler:
    def __init__(self, root_pid: int) -> None:
        self.root_pid = root_pid
        self.peak_rss_bytes = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="process-tree-rss", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(0.05):
            try:
                root = psutil.Process(self.root_pid)
                processes = [root, *root.children(recursive=True)]
                rss = sum(process.memory_info().rss for process in processes if process.is_running())
                self.peak_rss_bytes = max(self.peak_rss_bytes, rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect internal Granian free-threading and loop evidence.")
    parser.add_argument("--python", action="append", dest="pythons", help="Python version, repeatable")
    parser.add_argument("--loop", action="append", dest="loops", choices=["asyncio", "rloop", "uvloop", "winloop"])
    parser.add_argument(
        "--workers",
        default="1,2,logical",
        help="Comma-separated worker counts; use 'logical' for os.cpu_count()",
    )
    parser.add_argument("--workload", action="append", dest="workloads", choices=["cpu", "io"])
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--warmup", type=float, default=2.0)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--cpu-iterations", type=int, default=25_000)
    parser.add_argument("--io-delay", type=float, default=0.01)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_REPOSITORY_ROOT / ".agents" / "evidence" / "free-threading-loops",
    )
    return parser.parse_args()


def _worker_counts(value: str) -> list[int]:
    logical = os.cpu_count() or 1
    counts = {logical if item.strip() == "logical" else int(item) for item in value.split(",")}
    if any(count < 1 for count in counts):
        message = "worker counts must be positive"
        raise ValueError(message)
    return sorted(counts)


def _default_loops() -> list[str]:
    return ["asyncio", "winloop"] if sys.platform == "win32" else ["asyncio", "rloop", "uvloop"]


def _locked_version(package_name: str) -> tuple[int, ...] | None:
    lock_data = tomllib.loads((_REPOSITORY_ROOT / "uv.lock").read_text(encoding="utf-8"))
    for package in lock_data.get("package", []):
        if package.get("name") == package_name:
            return tuple(int(part) for part in package["version"].split(".") if part.isdigit())
    return None


def _eligible(python: str, loop: str) -> tuple[bool, str | None]:
    if loop == "winloop" and sys.platform != "win32":
        return False, "winloop is Windows-only"
    if loop in {"rloop", "uvloop"} and sys.platform == "win32":
        return False, f"{loop} is not selected on Windows"
    if loop == "uvloop" and python.endswith("t"):
        locked = _locked_version("uvloop")
        if locked is not None and locked <= (0, 22, 1):
            return False, "uvloop <=0.22.1 is quarantined on free-threaded Python (uvloop#720 / PR #721)"
    return True, None


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, process: subprocess.Popen[str], *, open_: bool) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.1)
            is_open = sock.connect_ex(("127.0.0.1", port)) == 0
        if is_open is open_:
            return
        if open_ and process.poll() is not None:
            output, _ = process.communicate()
            message = f"benchmark server exited before readiness ({process.returncode}):\n{output}"
            raise RuntimeError(message)
        time.sleep(0.05)
    message = f"port {port} did not become {'open' if open_ else 'closed'}"
    raise TimeoutError(message)


def _server_command(cell: _Cell, port: int) -> list[str]:
    command = [
        "uv",
        "run",
        "--isolated",
        "--frozen",
        "--python",
        cell.python,
        "--no-default-groups",
        "--group",
        "benchmark",
    ]
    if extra := _LOOP_EXTRAS.get(cell.loop):
        command.extend(("--extra", extra))
    command.extend((
        "python",
        "-m",
        "litestar",
        "--app",
        _APP,
        "run",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--workers",
        str(cell.workers),
        "--loop",
        cell.loop,
        "--workers-kill-timeout",
        "5",
    ))
    return command


def _start_server(cell: _Cell, port: int) -> subprocess.Popen[str]:
    options: dict[str, Any] = {
        "cwd": _REPOSITORY_ROOT,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
    }
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(_server_command(cell, port), **options)  # type: ignore[arg-type]
    _wait_for_port(port, process, open_=True)
    return process


def _litestar_parent(root_pid: int) -> psutil.Process:
    root = psutil.Process(root_pid)
    candidates = [root, *root.children(recursive=True)]
    for process in candidates:
        try:
            command = process.cmdline()
            if process.name().lower().startswith("python") and "litestar" in command and "run" in command:
                return process
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    message = "could not identify the Litestar parent process"
    raise RuntimeError(message)


def _taskkill_command(pid: int) -> list[str]:
    executable = shutil.which("taskkill") or str(
        Path(os.environ.get("SYSTEMROOT", "C:\\Windows")) / "System32" / "taskkill.exe"
    )
    return [executable, "/PID", str(pid), "/T", "/F"]


def _terminate_server(process: subprocess.Popen[str], port: int) -> tuple[float, str]:
    parent = _litestar_parent(process.pid)
    tree_pids = {
        child.pid
        for root in [psutil.Process(process.pid)]
        for child in [root, *root.children(recursive=True)]
        if child.is_running()
    }
    started = time.monotonic()
    if sys.platform == "win32":
        parent.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        os.kill(parent.pid, signal.SIGINT)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            subprocess.run(_taskkill_command(process.pid), check=False)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        raise
    shutdown_seconds = time.monotonic() - started
    _wait_for_port(port, process, open_=False)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(psutil.pid_exists(pid) for pid in tree_pids):
        time.sleep(0.05)
    remaining = sorted(pid for pid in tree_pids if psutil.pid_exists(pid))
    if remaining:
        message = f"benchmark process tree did not exit: {remaining}"
        raise RuntimeError(message)
    output = process.stdout.read() if process.stdout is not None else ""
    return shutdown_seconds, output


def _force_cleanup(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(_taskkill_command(process.pid), check=False)
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def _check_http2(port: int) -> None:
    connection = H2Connection()
    connection.initiate_connection()
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(connection.data_to_send())
        connection.send_headers(
            1,
            [
                (":method", "GET"),
                (":scheme", "http"),
                (":authority", f"127.0.0.1:{port}"),
                (":path", "/correctness/http2"),
            ],
            end_stream=True,
        )
        sock.sendall(connection.data_to_send())
        status: str | None = None
        body = bytearray()
        complete = False
        while not complete:
            data = sock.recv(65_535)
            if not data:
                break
            for event in connection.receive_data(data):
                if isinstance(event, ResponseReceived):
                    status = dict(event.headers).get(b":status", b"").decode()
                elif isinstance(event, DataReceived):
                    body.extend(event.data)
                    connection.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
                elif isinstance(event, StreamEnded):
                    complete = True
            pending = connection.data_to_send()
            if pending:
                sock.sendall(pending)
    if status != "200" or json.loads(body) != {"ok": True}:
        message = f"HTTP/2 correctness failed: status={status}, body={body!r}"
        raise RuntimeError(message)


def _check_websocket(port: int) -> None:
    with connect(f"ws://127.0.0.1:{port}/correctness/ws", open_timeout=5, close_timeout=5) as websocket_client:
        websocket_client.send("benchmark-correctness")
        if websocket_client.recv(timeout=5) != "benchmark-correctness":
            message = "WebSocket correctness round-trip failed"
            raise RuntimeError(message)


def _endpoint(cell: _Cell, port: int, args: argparse.Namespace) -> str:
    if cell.workload == "cpu":
        return f"http://127.0.0.1:{port}/cpu?iterations={args.cpu_iterations}"
    return f"http://127.0.0.1:{port}/io?delay={args.io_delay}"


def _run_load(url: str, *, duration: float, concurrency: int) -> tuple[int, int, list[float]]:
    deadline = time.monotonic() + duration
    latencies: list[float] = []
    errors = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal errors
        local_latencies: list[float] = []
        local_errors = 0
        with httpx.Client(timeout=5) as client:
            while time.monotonic() < deadline:
                started = time.perf_counter()
                try:
                    response = client.get(url)
                    response.raise_for_status()
                except httpx.HTTPError:
                    local_errors += 1
                else:
                    local_latencies.append((time.perf_counter() - started) * 1000)
        with lock:
            latencies.extend(local_latencies)
            errors += local_errors

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(concurrency)]
        for future in futures:
            future.result()
    return len(latencies), errors, latencies


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1))
    return round(ordered[index], 3)


def _run_cell(cell: _Cell, args: argparse.Namespace) -> dict[str, Any]:
    port = _free_port()
    process = _start_server(cell, port)
    sampler = _ProcessTreeSampler(process.pid)
    sampler.start()
    output = ""
    try:
        _check_http2(port)
        _check_websocket(port)
        warmup_deadline = time.monotonic() + args.warmup
        with httpx.Client(timeout=5) as client:
            while time.monotonic() < warmup_deadline:
                client.get(_endpoint(cell, port, args)).raise_for_status()
        requests, errors, latencies = _run_load(
            _endpoint(cell, port, args),
            duration=args.duration,
            concurrency=args.concurrency,
        )
        shutdown_seconds, output = _terminate_server(process, port)
    finally:
        sampler.stop()
        _force_cleanup(process)
    if process.returncode != 0:
        message = f"benchmark server exited with {process.returncode}:\n{output}"
        raise RuntimeError(message)
    return {
        "python": cell.python,
        "loop": cell.loop,
        "workers": cell.workers,
        "workload": cell.workload,
        "duration_seconds": args.duration,
        "requests": requests,
        "errors": errors,
        "throughput_rps": round(requests / args.duration, 3),
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
        },
        "peak_process_tree_rss_bytes": sampler.peak_rss_bytes,
        "shutdown_seconds": round(shutdown_seconds, 3),
    }


def main() -> None:
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(prefix=".write-check-", dir=args.output_dir):
            pass
    except OSError as exc:
        message = f"evidence directory is not writable: {args.output_dir}"
        raise PermissionError(message) from exc
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_path = args.output_dir / f"{timestamp}.json"
    pythons = args.pythons or ["3.14", "3.14t"]
    loops = args.loops or _default_loops()
    workloads = args.workloads or ["cpu", "io"]
    cells = [
        _Cell(python, loop, workers, workload)
        for python in pythons
        for loop in loops
        for workers in _worker_counts(args.workers)
        for workload in workloads
    ]
    results: list[dict[str, Any]] = []
    for cell in cells:
        eligible, reason = _eligible(cell.python, cell.loop)
        if not eligible:
            print(f"SKIP {cell}: {reason}")
            continue
        print(f"RUN {cell}")
        results.append(_run_cell(cell, args))
        evidence_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not evidence_path.exists():
        evidence_path.write_text("[]\n", encoding="utf-8")
    print(evidence_path)


if __name__ == "__main__":
    main()
