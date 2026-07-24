from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import sysconfig
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from websockets.sync.client import connect

from tests.integration._runtime import (
    descendants,
    finish_process,
    free_port,
    start_process,
    terminate_process_group,
    wait_for_descendants_to_exit,
    wait_for_port,
)

if TYPE_CHECKING:
    from tests.conftest import CreateAppFileFixture

pytestmark = pytest.mark.skipif(
    sysconfig.get_config_var("Py_GIL_DISABLED") != 1,
    reason="free-threaded runtime stress requires a Py_GIL_DISABLED build",
)

_APP = """
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from litestar import Litestar, WebSocket, get, websocket
from litestar.logging import LoggingConfig
from litestar.plugins import CLIPlugin

from litestar_granian import GranianPlugin

events_path = Path(os.environ["FREE_THREADED_EVENTS"])
parent_marker = Path(os.environ["FREE_THREADED_PARENT_MARKER"])
event_lock = threading.Lock()
request_context: ContextVar[str | None] = ContextVar("request_context", default=None)


def append_event(event: str, request_id: str | None = None) -> None:
    payload = {
        "event": event,
        "pid": os.getpid(),
        "thread_id": threading.get_native_id(),
        "request_id": request_id,
    }
    with event_lock, events_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\\n")


def append_parent_marker(event: str) -> None:
    with parent_marker.open("a", encoding="utf-8") as stream:
        stream.write(f"{event}:{os.getpid()}\\n")


class RequestJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "event": record.getMessage(),
                "request_id": getattr(record, "request_id", None),
                "thread_id": getattr(record, "thread_id", None),
            },
            sort_keys=True,
        )


class ParentLifespanRecorder(CLIPlugin):
    @contextmanager
    def server_lifespan(self, app: Litestar):
        append_parent_marker("sidecar-start")
        try:
            yield
        finally:
            append_parent_marker("sidecar-stop")


def startup() -> None:
    append_event("startup")


def shutdown() -> None:
    if os.environ.get("FREE_THREADED_STUCK_SHUTDOWN"):
        time.sleep(60)
    append_event("shutdown")


@get("/work/{request_id:str}")
async def work(request_id: str) -> dict[str, str | None]:
    token = request_context.set(request_id)
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        observed = request_context.get()
        append_event("request", observed)
        logging.getLogger("stress").info(
            "stress-request",
            extra={"request_id": observed, "thread_id": threading.get_native_id()},
        )
        return {"request_id": observed}
    finally:
        request_context.reset(token)


@websocket("/ws")
async def echo(socket: WebSocket) -> None:
    await socket.accept()
    await socket.send_text(await socket.receive_text())
    await socket.close()


logging_config = LoggingConfig(
    formatters={"stress": {"()": RequestJSONFormatter}},
    handlers={"stress": {"class": "logging.StreamHandler", "formatter": "stress", "stream": "ext://sys.stdout"}},
    loggers={
        "litestar": {"level": "INFO", "handlers": ["stress"], "propagate": False},
        "stress": {"level": "INFO", "handlers": ["stress"], "propagate": False},
    },
)

app = Litestar(
    route_handlers=[work, echo],
    plugins=[GranianPlugin(), ParentLifespanRecorder()],
    logging_config=logging_config,
    on_startup=[startup],
    on_shutdown=[shutdown],
)
"""


@dataclass
class _RunningServer:
    process: subprocess.Popen[str]
    port: int
    events_path: Path
    parent_marker: Path
    temporary_directory: Path
    descendant_pids: set[int]


def _read_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _wait_for_events(path: Path, event: str, count: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if sum(record.get("event") == event for record in _read_json_lines(path)) >= count:
            return
        time.sleep(0.05)
    message = f"event {event!r} did not appear {count} times in {path}"
    raise AssertionError(message)


def _start_server(
    *,
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
    tmp_path: Path,
    name: str,
    extra_args: Iterable[str] = (),
    extra_env: dict[str, str] | None = None,
) -> _RunningServer:
    app_file = create_app_file(f"free_threaded_{name}.py", content=_APP)
    events_path = tmp_path / f"{name}-events.jsonl"
    parent_marker = tmp_path / f"{name}-parent.txt"
    temporary_directory = tmp_path / f"{name}-temp"
    temporary_directory.mkdir()
    port = free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_project_dir), env.get("PYTHONPATH", "")))
    env["PYTHONUNBUFFERED"] = "1"
    env["FREE_THREADED_EVENTS"] = str(events_path)
    env["FREE_THREADED_PARENT_MARKER"] = str(parent_marker)
    env["TMPDIR"] = str(temporary_directory)
    env["TEMP"] = str(temporary_directory)
    env["TMP"] = str(temporary_directory)
    if extra_env:
        env.update(extra_env)
    command = [
        sys.executable,
        "-m",
        "litestar",
        "--app",
        f"{app_file.stem}:app",
        "run",
        "--port",
        str(port),
        "--workers",
        "2",
        "--loop",
        "asyncio",
        "--workers-kill-timeout",
        "1",
        *extra_args,
    ]
    process = start_process(command, cwd=tmp_project_dir, env=env)
    try:
        wait_for_port(port, process, open_=True)
        _wait_for_events(events_path, "startup", 2)
    except BaseException:
        terminate_process_group(process)
        raise
    return _RunningServer(
        process=process,
        port=port,
        events_path=events_path,
        parent_marker=parent_marker,
        temporary_directory=temporary_directory,
        descendant_pids=descendants(process.pid),
    )


def _stop_server(server: _RunningServer, *, timeout: float = 12) -> str:
    if sys.platform == "win32":
        server.process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        os.kill(server.process.pid, signal.SIGINT)
    output = finish_process(server.process, timeout)
    wait_for_port(server.port, server.process, open_=False)
    wait_for_descendants_to_exit(server.descendant_pids, parent_pid=server.process.pid)
    return output


def _request(port: int, request_id: str, connection: HTTPConnection | None = None) -> str | None:
    owns_connection = connection is None
    connection = connection or HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", f"/work/{request_id}")
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        request_value = payload["request_id"]
        assert request_value is None or isinstance(request_value, str)
        return request_value
    finally:
        if owns_connection:
            connection.close()


def _request_reused(port: int, request_ids: list[str]) -> list[str | None]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        return [_request(port, request_id, connection) for request_id in request_ids]
    finally:
        connection.close()


def _parse_structured_output(output: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


def _assert_parent_lifecycle(server: _RunningServer) -> None:
    markers = server.parent_marker.read_text(encoding="utf-8").splitlines()
    starts = [line for line in markers if line.startswith("sidecar-start:")]
    stops = [line for line in markers if line.startswith("sidecar-stop:")]
    assert len(starts) == 1
    assert len(stops) == 1
    assert starts[0].split(":", 1)[1] == stops[0].split(":", 1)[1]


def test_shared_workers_isolate_request_context_and_structured_logging(
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
    tmp_path: Path,
) -> None:
    server = _start_server(
        create_app_file=create_app_file,
        tmp_project_dir=tmp_project_dir,
        tmp_path=tmp_path,
        name="shared-state",
    )
    output = ""
    try:
        fresh_ids = [f"fresh-{index}" for index in range(50)]
        reused_groups = [[f"reused-{group}-{index}" for index in range(5)] for group in range(10)]
        with ThreadPoolExecutor(max_workers=20) as executor:
            fresh_results = list(executor.map(lambda request_id: _request(server.port, request_id), fresh_ids))
            reused_results = list(
                executor.map(lambda request_ids: _request_reused(server.port, request_ids), reused_groups)
            )

        expected = set(fresh_ids) | {request_id for group in reused_groups for request_id in group}
        observed = set(fresh_results) | {request_id for group in reused_results for request_id in group}
        assert observed == expected
        output = _stop_server(server)
    finally:
        terminate_process_group(server.process)

    events = _read_json_lines(server.events_path)
    startups = [record for record in events if record["event"] == "startup"]
    requests = [record for record in events if record["event"] == "request"]
    assert len(startups) == 2
    assert len({record["pid"] for record in startups}) == 1
    assert len({record["thread_id"] for record in startups}) == 2
    child_pid = startups[0]["pid"]
    assert child_pid in server.descendant_pids
    assert len(requests) == 100
    assert {record["request_id"] for record in requests} == expected

    _assert_parent_lifecycle(server)
    parent_pid = int(server.parent_marker.read_text(encoding="utf-8").splitlines()[0].split(":", 1)[1])
    assert parent_pid != child_pid

    structured_records = _parse_structured_output(output)
    request_logs = [record for record in structured_records if record.get("event") == "stress-request"]
    assert len(request_logs) == 100
    assert {record["request_id"] for record in request_logs} == expected


def test_outer_deadline_reaps_child_with_stuck_worker_shutdown(
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
    tmp_path: Path,
) -> None:
    server = _start_server(
        create_app_file=create_app_file,
        tmp_project_dir=tmp_project_dir,
        tmp_path=tmp_path,
        name="stuck-shutdown",
        extra_env={"FREE_THREADED_STUCK_SHUTDOWN": "1"},
    )
    started = time.monotonic()
    try:
        output = _stop_server(server)
    finally:
        terminate_process_group(server.process)

    assert time.monotonic() - started < 10
    assert server.process.returncode != 0, output
    _assert_parent_lifecycle(server)


def test_ten_start_request_stop_cycles_leave_no_runtime_artifacts(
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
    tmp_path: Path,
) -> None:
    for cycle in range(10):
        server = _start_server(
            create_app_file=create_app_file,
            tmp_project_dir=tmp_project_dir,
            tmp_path=tmp_path,
            name=f"cycle-{cycle}",
        )
        try:
            assert _request(server.port, f"cycle-{cycle}") == f"cycle-{cycle}"
            _stop_server(server)
        finally:
            terminate_process_group(server.process)
        _assert_parent_lifecycle(server)
        assert not list(server.temporary_directory.glob("litestar-granian-*.json"))


@pytest.mark.upstream
@pytest.mark.timeout(30)
@pytest.mark.xfail(reason="Granian #881: repeated free-threaded metrics lifecycle can panic", strict=False)
def test_granian_881_repeated_metrics_lifecycle_diagnostic(
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
    tmp_path: Path,
) -> None:
    outputs: list[str] = []
    for cycle in range(3):
        metrics_port = free_port()
        server = _start_server(
            create_app_file=create_app_file,
            tmp_project_dir=tmp_project_dir,
            tmp_path=tmp_path,
            name=f"metrics-{cycle}",
            extra_args=("--metrics", "--metrics-port", str(metrics_port)),
        )
        try:
            outputs.append(_stop_server(server))
        finally:
            terminate_process_group(server.process)
        _assert_parent_lifecycle(server)
    output = "\n".join(outputs)
    assert "panicked at" not in output, output


@pytest.mark.upstream
@pytest.mark.timeout(30)
@pytest.mark.parametrize("runtime_mode", ["mt", "st"])
@pytest.mark.xfail(reason="Granian #884: free-threaded WebSocket teardown can panic", strict=False)
def test_granian_884_websocket_teardown_diagnostic(
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
    tmp_path: Path,
    runtime_mode: str,
) -> None:
    server = _start_server(
        create_app_file=create_app_file,
        tmp_project_dir=tmp_project_dir,
        tmp_path=tmp_path,
        name=f"websocket-{runtime_mode}",
        extra_args=("--runtime-mode", runtime_mode),
    )
    output = ""
    try:
        with connect(f"ws://127.0.0.1:{server.port}/ws", open_timeout=5, close_timeout=5) as websocket_client:
            websocket_client.send(runtime_mode)
            assert websocket_client.recv(timeout=5) == runtime_mode
        output = _stop_server(server)
    finally:
        terminate_process_group(server.process)
    _assert_parent_lifecycle(server)
    assert "panicked at" not in output, output


@pytest.mark.upstream
@pytest.mark.timeout(30)
@pytest.mark.xfail(reason="Granian #875: free-threaded workers can miss ASGI shutdown hooks", strict=False)
def test_granian_875_runs_every_worker_shutdown_hook_diagnostic(
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
    tmp_path: Path,
) -> None:
    server = _start_server(
        create_app_file=create_app_file,
        tmp_project_dir=tmp_project_dir,
        tmp_path=tmp_path,
        name="shutdown-hooks",
    )
    output = ""
    try:
        output = _stop_server(server)
    finally:
        terminate_process_group(server.process)
    _assert_parent_lifecycle(server)
    shutdowns = [record for record in _read_json_lines(server.events_path) if record["event"] == "shutdown"]
    assert len(shutdowns) == 2, output
