from __future__ import annotations

import csv
import io
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(port: int, process: subprocess.Popen[str] | None = None, *, open_: bool) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.1)
            is_open = sock.connect_ex(("127.0.0.1", port)) == 0
        if is_open is open_:
            return
        if open_ and process is not None and process.poll() is not None:
            stdout, _ = process.communicate()
            message = f"server exited before readiness ({process.returncode}):\n{stdout}"
            raise AssertionError(message)
        time.sleep(0.05)
    message = f"port {port} did not become {'open' if open_ else 'closed'}"
    if process is not None:
        returncode = process.poll()
        liveness = "still running" if returncode is None else f"already exited with code {returncode}"
        message += f" (pid {process.pid} {liveness})"
    raise AssertionError(message)


def windows_executable(name: str, *parts: str) -> str:
    located = shutil.which(name)
    if located is not None:
        return located
    return str(Path(os.environ.get("SYSTEMROOT", "C:\\Windows")).joinpath(*parts, f"{name}.exe"))


def descendants(root_pid: int) -> set[int]:
    if sys.platform == "win32":
        powershell = windows_executable(
            "powershell",
            "System32",
            "WindowsPowerShell",
            "v1.0",
        )
        script = (
            "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId | ConvertTo-Csv -NoTypeInformation"
        )
        output = subprocess.check_output([powershell, "-NoProfile", "-Command", script], text=True)
        rows = csv.DictReader(io.StringIO(output))
        pairs = [(int(row["ProcessId"]), int(row["ParentProcessId"])) for row in rows]
    else:
        ps = shutil.which("ps") or "/bin/ps"
        output = subprocess.check_output([ps, "-eo", "pid=,ppid="], text=True)
        pairs = [
            (int(pid_text), int(parent_text))
            for line in output.splitlines()
            for pid_text, parent_text in [line.split()]
        ]

    by_parent: dict[int, set[int]] = {}
    for pid, parent_pid in pairs:
        by_parent.setdefault(parent_pid, set()).add(pid)
    found: set[int] = set()
    pending = [root_pid]
    while pending:
        parent = pending.pop()
        for child in by_parent.get(parent, ()):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def pid_exists(pid: int) -> bool:
    if sys.platform == "win32":
        tasklist = windows_executable("tasklist", "System32")
        output = subprocess.check_output(
            [tasklist, "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True,
        )
        return any(len(row) > 1 and row[1] == str(pid) for row in csv.reader(io.StringIO(output)))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_for_descendants_to_exit(pids: set[int], *, parent_pid: int | None = None) -> None:
    def current_pids() -> set[int]:
        if parent_pid is not None and pid_exists(parent_pid):
            return descendants(parent_pid)
        return pids

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if all(not pid_exists(pid) for pid in current_pids()):
            return
        time.sleep(0.05)
    remaining = sorted(pid for pid in current_pids() if pid_exists(pid))
    message = f"Granian descendants did not exit: {remaining}"
    raise AssertionError(message)


def wait_for_markers(marker: Path, value: str, count: int, *, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists() and marker.read_text(encoding="utf-8").splitlines().count(value) >= count:
            return
        time.sleep(0.05)
    message = f"marker {value!r} did not appear {count} times"
    raise AssertionError(message)


def start_process(command: Sequence[str], *, cwd: Path, env: Mapping[str, str]) -> subprocess.Popen[str]:
    if sys.platform == "win32":
        return subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def finish_process(process: subprocess.Popen[str], timeout: float) -> str:
    stdout, _ = process.communicate(timeout=timeout)
    return stdout if stdout is not None else ""


def terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        taskkill = windows_executable("taskkill", "System32")
        subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"], check=False)
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)
