from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from litestar_granian.logging import build_logging_config


class ProcessFormatter(logging.Formatter):
    """Formatter used to verify reconstruction across a process boundary."""

    def format(self, record: logging.LogRecord) -> str:
        return f"process::{record.levelname.lower()}::{record.getMessage()}"


def test_recreated_formatter_works_in_a_fresh_process(tmp_path: Path) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(ProcessFormatter())
    logger = logging.getLoggerClass()("litestar")
    logger.handlers = [handler]
    logger.propagate = False
    config = build_logging_config(None, logger=logger)
    assert config is not None
    config_path = tmp_path / "logging.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    script = """
import json
import logging
import logging.config
import sys

with open(sys.argv[1], encoding="utf-8") as config_file:
    logging.config.dictConfig(json.load(config_file))
logging.getLogger("_granian").warning("served %s", "request")
"""

    completed = subprocess.run(
        [sys.executable, "-c", script, str(config_path)],
        check=True,
        capture_output=True,
        cwd=Path(__file__).parents[2],
        text=True,
    )

    assert completed.stdout.strip() == "process::warning::served request"


def test_logging_module_import_does_not_require_structlog() -> None:
    script = """
import builtins

original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "structlog" or name.startswith("structlog."):
        raise AssertionError("production logging imported structlog")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import litestar_granian.logging
"""

    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        cwd=Path(__file__).parents[2],
        text=True,
    )
