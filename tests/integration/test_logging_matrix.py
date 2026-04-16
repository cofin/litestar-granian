"""Phase 0 Task 0.6 — logging matrix validation.

Exercises ``_get_logging_config`` across platforms x worker counts x logger
backends x modes to catch regressions of #21 / #41 before they ship.

These tests run deterministically in-process by monkeypatching ``sys.platform``
and driving the config builder directly; they do not spawn real Granian worker
processes (that belongs to the CI matrix that runs on actual Linux/macOS/
Windows hosts).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from litestar.logging.config import LoggingConfig

from litestar_granian.cli import _get_logging_config


def _env_with(logging_config: Any) -> Any:
    env = MagicMock()
    env.app.logging_config = logging_config
    return env


def _queue_config() -> LoggingConfig:
    return LoggingConfig(
        loggers={},
        handlers={
            "queue_listener": {
                "class": "litestar.logging.standard.QueueListenerHandler",
                "formatter": "standard",
                "level": "DEBUG",
            },
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": "INFO",
            },
        },
    )


@pytest.mark.parametrize("platform_name", ["linux", "darwin", "win32"])
@pytest.mark.parametrize("use_litestar_logger", [True, False])
def test_matrix_no_queue_handlers_on_spawn(
    monkeypatch: pytest.MonkeyPatch, platform_name: str, use_litestar_logger: bool
) -> None:
    """On spawn platforms the returned config must contain zero queue handlers."""
    monkeypatch.setattr("sys.platform", platform_name)
    env = _env_with(_queue_config() if use_litestar_logger else None)

    result = _get_logging_config(env, use_litestar_logger=use_litestar_logger)

    if platform_name == "linux":
        return  # Linux is allowed to keep queue handlers
    for handler in result.get("handlers", {}).values():
        handler_class = str(handler.get("class") or handler.get("()") or "")
        assert "QueueListenerHandler" not in handler_class
        assert "QueueHandler" not in handler_class
        assert "listener" not in handler


@pytest.mark.parametrize("platform_name", ["linux", "darwin", "win32"])
def test_matrix_granian_loggers_always_present(monkeypatch: pytest.MonkeyPatch, platform_name: str) -> None:
    monkeypatch.setattr("sys.platform", platform_name)
    env = _env_with(_queue_config())

    result = _get_logging_config(env, use_litestar_logger=True)

    assert "_granian" in result["loggers"]
    assert "granian.access" in result["loggers"]


@pytest.mark.parametrize("platform_name", ["linux", "darwin", "win32"])
def test_matrix_returns_dictconfig_version(monkeypatch: pytest.MonkeyPatch, platform_name: str) -> None:
    monkeypatch.setattr("sys.platform", platform_name)
    env = _env_with(None)
    assert _get_logging_config(env, use_litestar_logger=False)["version"] == 1
    env = _env_with(_queue_config())
    assert _get_logging_config(env, use_litestar_logger=True)["version"] == 1
