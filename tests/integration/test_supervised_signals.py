from __future__ import annotations

import os
import signal
import sys
import sysconfig
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.integration._runtime import (
    descendants,
    free_port,
    start_process,
    terminate_process_group,
    wait_for_descendants_to_exit,
    wait_for_markers,
    wait_for_port,
)

if TYPE_CHECKING:
    from tests.conftest import CreateAppFileFixture

_APP = """
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path

from litestar import Litestar, get
from litestar.logging import LoggingConfig, StructLoggingConfig
from litestar.plugins import CLIPlugin

from litestar_granian import GranianPlugin

marker = Path(os.environ["SUPERVISOR_MARKER"])


def append_marker(value: str) -> None:
    with marker.open("a", encoding="utf-8") as stream:
        stream.write(value + "\\n")


class LifespanRecorder(CLIPlugin):
    @contextmanager
    def server_lifespan(self, app: Litestar):
        append_marker("sidecar-start")
        try:
            yield
        finally:
            append_marker("sidecar-stop")


def app_shutdown() -> None:
    if os.environ.get("SUPERVISOR_STUCK_SHUTDOWN"):
        time.sleep(60)
    append_marker("app-stop")


def app_startup() -> None:
    append_marker("app-start")


@get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app = Litestar(
    route_handlers=[health],
    plugins=[GranianPlugin(), LifespanRecorder()],
    logging_config=StructLoggingConfig() if os.environ.get("SUPERVISOR_STRUCTURED") else LoggingConfig(),
    on_startup=[app_startup],
    on_shutdown=[app_shutdown],
)
"""


_WINDOWS_BREAK = getattr(signal, "CTRL_BREAK_EVENT", signal.SIGINT)
_FREE_THREADED = sysconfig.get_config_var("Py_GIL_DISABLED") == 1
_CASES = (
    [
        pytest.param(1, _WINDOWS_BREAK, False, True, False, id="break-one-worker-structlog"),
        pytest.param(2, _WINDOWS_BREAK, False, True, False, id="break-two-workers-structlog"),
        pytest.param(1, _WINDOWS_BREAK, True, False, False, id="break-reload-standard"),
        pytest.param(1, _WINDOWS_BREAK, False, False, True, id="repeated-break-forced"),
    ]
    if sys.platform == "win32"
    else [
        pytest.param(1, signal.SIGINT, False, True, False, id="sigint-one-worker-structlog"),
        pytest.param(2, signal.SIGINT, False, True, False, id="sigint-two-workers-structlog"),
        pytest.param(1, signal.SIGTERM, False, True, False, id="sigterm-one-worker-structlog"),
        pytest.param(2, signal.SIGTERM, False, True, False, id="sigterm-two-workers-structlog"),
        *([] if _FREE_THREADED else [pytest.param(1, signal.SIGINT, True, False, False, id="sigint-reload-standard")]),
        pytest.param(1, signal.SIGINT, False, False, True, id="repeated-sigint-forced"),
    ]
)


@pytest.mark.parametrize(("workers", "termination_signal", "reload", "structured", "repeat_signal"), _CASES)
def test_parent_only_signal_reaps_granian_and_unwinds_lifespans(
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
    tmp_path: Path,
    workers: int,
    termination_signal: int,
    reload: bool,
    structured: bool,
    repeat_signal: bool,
) -> None:
    app_file = create_app_file(
        f"supervised_{workers}_{termination_signal}_{reload}_{repeat_signal}.py",
        content=_APP,
    )
    marker = tmp_path / "lifespan.txt"
    port = free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_project_dir), env.get("PYTHONPATH", "")))
    env["SUPERVISOR_MARKER"] = str(marker)
    env["PYTHONUNBUFFERED"] = "1"
    if structured:
        env["SUPERVISOR_STRUCTURED"] = "1"
    if repeat_signal:
        env["SUPERVISOR_STUCK_SHUTDOWN"] = "1"
    extra_args = ["--reload"] if reload else []
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
        str(workers),
        "--workers-kill-timeout",
        "1",
        *extra_args,
    ]
    process = start_process(command, cwd=tmp_project_dir, env=env)

    try:
        wait_for_port(port, process, open_=True)
        wait_for_markers(marker, "app-start", workers)
        descendant_pids = descendants(process.pid)
        if sys.platform == "win32":
            process.send_signal(termination_signal)
        else:
            os.kill(process.pid, termination_signal)
        if repeat_signal:
            time.sleep(0.2)
            if sys.platform == "win32":
                process.send_signal(termination_signal)
            else:
                os.kill(process.pid, termination_signal)
        process.wait(timeout=12)
        wait_for_port(port, process, open_=False)
        output = process.stdout.read() if process.stdout is not None else ""

        lines = marker.read_text(encoding="utf-8").splitlines()
        assert lines.count("sidecar-start") == 1
        assert lines.count("sidecar-stop") == 1
        graceful_workers = lines.count("app-stop")
        if repeat_signal:
            assert graceful_workers < workers
        elif _FREE_THREADED:
            # Granian #875: free-threaded workers can report a clean thread
            # stop without running every ASGI shutdown hook.
            assert 0 <= graceful_workers <= workers
            if graceful_workers < workers:
                assert "free-threaded Python support is experimental!" in output
                assert all(f"Stopped worker-{worker}" in output for worker in range(1, workers + 1))
        else:
            # Granian #875: each worker that misses its ASGI shutdown hook
            # must be explicitly accounted for by Granian's forced-kill path.
            assert 0 <= graceful_workers <= workers
            if graceful_workers < workers:
                assert output.count("Killing worker-") >= workers - graceful_workers
        wait_for_descendants_to_exit(descendant_pids)
    finally:
        terminate_process_group(process)
