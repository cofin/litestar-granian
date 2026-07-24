from __future__ import annotations

import json
import os
import signal
import sys
from typing import TYPE_CHECKING

import pytest

from tests.integration._runtime import finish_process, free_port, start_process, terminate_process_group, wait_for_port

if TYPE_CHECKING:
    from pathlib import Path

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
