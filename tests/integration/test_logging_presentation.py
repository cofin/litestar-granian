from __future__ import annotations

import json
import os
import signal
import sys
import sysconfig
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.integration._runtime import finish_process, free_port, start_process, terminate_process_group, wait_for_port

if TYPE_CHECKING:
    from tests.conftest import CreateAppFileFixture

_APP = """
from __future__ import annotations

import logging
import os
from typing import Any

import structlog
from litestar import Litestar, get
from litestar.logging import LoggingConfig, StructLoggingConfig

from litestar_granian import GranianPlugin


class PrefixFormatter(logging.Formatter):
    def __init__(self, *, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def format(self, record: logging.LogRecord) -> str:
        return f"{self.prefix}::{record.name}::{record.levelname.lower()}::{record.getMessage()}"


class AddApplicationFields:
    def __init__(self, application: str) -> None:
        self.application = application

    def __call__(self, _: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict["application"] = self.application
        return event_dict


def make_logging_config() -> LoggingConfig | StructLoggingConfig:
    if os.environ.get("CUSTOM_STRUCTURED"):
        return StructLoggingConfig(
            standard_lib_logging_config=LoggingConfig(
                formatters={
                    "custom": {
                        "()": "structlog.stdlib.ProcessorFormatter",
                        "processors": [
                            AddApplicationFields("application-shape"),
                            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                            structlog.processors.JSONRenderer(sort_keys=True),
                        ],
                    }
                },
                handlers={"custom_console": {"class": "logging.StreamHandler", "formatter": "custom"}},
                loggers={"litestar": {"level": "INFO", "handlers": ["custom_console"], "propagate": False}},
            )
        )
    return LoggingConfig(
        formatters={"custom": {"()": PrefixFormatter, "prefix": "application-shape"}},
        handlers={"custom_console": {"class": "logging.StreamHandler", "formatter": "custom"}},
        loggers={"litestar": {"level": "INFO", "handlers": ["custom_console"], "propagate": False}},
    )


@get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app = Litestar(
    route_handlers=[health],
    plugins=[GranianPlugin()],
    logging_config=make_logging_config(),
)
"""

_RELOAD_APP = """
from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path

from litestar import Litestar, get
from litestar.logging import LoggingConfig
from litestar.plugins import CLIPlugin

from litestar_granian import GranianPlugin

worker_marker = Path(os.environ["RELOAD_WORKER_MARKER"])
parent_marker = Path(os.environ["RELOAD_PARENT_MARKER"])


class ReloadFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return f"reload-shape::{record.name}::{record.levelname.lower()}::{record.getMessage()}"


def snapshot(event: str) -> None:
    payload = {
        "event": event,
        "pid": os.getpid(),
    }
    with parent_marker.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\\n")


class ParentLifespanRecorder(CLIPlugin):
    @contextmanager
    def server_lifespan(self, app: Litestar):
        snapshot("parent-start")
        try:
            yield
        finally:
            snapshot("parent-stop")


def worker_startup() -> None:
    with worker_marker.open("a", encoding="utf-8") as stream:
        stream.write("worker-start\\n")
    logging.getLogger("_granian").warning("worker-start")


@get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


logging_config = LoggingConfig(
    formatters={"reload": {"()": ReloadFormatter}},
    handlers={
        "reload_output": {
            "class": "logging.StreamHandler",
            "formatter": "reload",
            "stream": "ext://sys.stdout",
        },
        "queue_listener": {
            "class": "logging.handlers.QueueHandler",
            "queue": {"()": "queue.Queue", "maxsize": -1},
            "listener": "litestar.logging.standard.LoggingQueueListener",
            "handlers": ["reload_output"],
        },
    },
    loggers={"litestar": {"level": "INFO", "handlers": ["queue_listener"], "propagate": False}},
)

app = Litestar(
    route_handlers=[health],
    plugins=[GranianPlugin(), ParentLifespanRecorder()],
    logging_config=logging_config,
    on_startup=[worker_startup],
)
"""


def _wait_for_worker_starts(marker: Path, count: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if marker.exists() and marker.read_text(encoding="utf-8").splitlines().count("worker-start") >= count:
            return
        time.sleep(0.05)
    message = f"worker did not start {count} times"
    raise AssertionError(message)


@pytest.mark.parametrize("structured", [False, True], ids=["custom-formatter", "structlog-processors"])
def test_supervised_child_matches_custom_litestar_formatter(
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
    structured: bool,
) -> None:
    app_file = create_app_file(f"custom_logging_{structured}.py", content=_APP)
    port = free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_project_dir), env.get("PYTHONPATH", "")))
    env["PYTHONUNBUFFERED"] = "1"
    if structured:
        env["CUSTOM_STRUCTURED"] = "1"
    command = [
        sys.executable,
        "-m",
        "litestar",
        "--app",
        f"{app_file.stem}:app",
        "run",
        "--port",
        str(port),
        "--workers-kill-timeout",
        "1",
    ]
    process = start_process(command, cwd=tmp_project_dir, env=env)

    try:
        wait_for_port(port, process, open_=True)
        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.kill(process.pid, signal.SIGINT)
        output = finish_process(process, timeout=12)

        if structured:
            payloads = [
                payload
                for line in output.splitlines()
                if line.startswith("{")
                for payload in [json.loads(line)]
                if payload.get("application") == "application-shape"
            ]
            assert payloads
        else:
            assert "application-shape::_granian::info::" in output
    finally:
        terminate_process_group(process)


@pytest.mark.skipif(
    sysconfig.get_config_var("Py_GIL_DISABLED") == 1, reason="Granian reload rejects free-threaded Python"
)
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows records the reload parent lifespan under a different PID; under investigation",
)
def test_file_reload_reuses_one_formatter_config_and_parent_lifespan(
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
    tmp_path: Path,
) -> None:
    app_file = create_app_file("reload_logging.py", content=_RELOAD_APP)
    worker_marker = tmp_path / "worker-starts.txt"
    parent_marker = tmp_path / "parent-lifespan.jsonl"
    temporary_directory = tmp_path / "temporary"
    temporary_directory.mkdir()
    port = free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_project_dir), env.get("PYTHONPATH", "")))
    env["PYTHONUNBUFFERED"] = "1"
    env["RELOAD_WORKER_MARKER"] = str(worker_marker)
    env["RELOAD_PARENT_MARKER"] = str(parent_marker)
    env["TMPDIR"] = str(temporary_directory)
    env["TEMP"] = str(temporary_directory)
    env["TMP"] = str(temporary_directory)
    command = [
        sys.executable,
        "-m",
        "litestar",
        "--app",
        f"{app_file.stem}:app",
        "run",
        "--port",
        str(port),
        "--workers-kill-timeout",
        "1",
        "--reload",
        "--reload-tick",
        "50",
    ]
    process = start_process(command, cwd=tmp_project_dir, env=env)
    initial_configs: list[Path] = []
    reloaded_configs: list[Path] = []

    try:
        wait_for_port(port, process, open_=True)
        _wait_for_worker_starts(worker_marker, 1)
        initial_configs = list(temporary_directory.glob("litestar-granian-*.json"))
        time.sleep(0.2)
        app_file.write_text(f"{_RELOAD_APP}\n# file-triggered reload\n", encoding="utf-8")
        _wait_for_worker_starts(worker_marker, 2)
        reloaded_configs = list(temporary_directory.glob("litestar-granian-*.json"))
        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.kill(process.pid, signal.SIGINT)
        output = finish_process(process, timeout=12)
        wait_for_port(port, process, open_=False)
    finally:
        terminate_process_group(process)

    snapshots = [json.loads(line) for line in parent_marker.read_text(encoding="utf-8").splitlines()]
    starts = [snapshot for snapshot in snapshots if snapshot["event"] == "parent-start"]
    stops = [snapshot for snapshot in snapshots if snapshot["event"] == "parent-stop"]
    assert len(starts) == 1
    assert len(stops) == 1
    assert starts[0]["pid"] == stops[0]["pid"] == process.pid
    assert len(initial_configs) == 1
    assert reloaded_configs == initial_configs
    assert output.count("reload-shape::_granian::warning::worker-start") >= 2
    assert not list(temporary_directory.glob("litestar-granian-*.json"))
