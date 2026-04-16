"""Tests for ``_get_logging_config`` — the choke-point for Granian logging.

Covers Phase 0 tasks 0.1 (no mutation), 0.2 (platform-aware queue handlers), and
0.3 (respect user-configured loggers).
"""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import MagicMock

import pytest
from granian.log import LOGGING_CONFIG
from litestar.logging.config import LoggingConfig

from litestar_granian.cli import _get_logging_config, _neutralize_queue_handlers_for_platform


def _make_env(app_logging_config: Any) -> Any:
    env = MagicMock()
    env.app.logging_config = app_logging_config
    return env


def test_get_logging_config_does_not_mutate_module_config() -> None:
    """Phase 0 Task 0.1: repeated calls must not mutate ``granian.log.LOGGING_CONFIG``."""
    frozen = copy.deepcopy(LOGGING_CONFIG)
    env = _make_env(LoggingConfig(loggers={}))

    _get_logging_config(env, use_litestar_logger=True)
    _get_logging_config(env, use_litestar_logger=True)

    assert LOGGING_CONFIG == frozen


def test_get_logging_config_preserves_user_granian_level() -> None:
    """Phase 0 Task 0.3: if user set ``_granian`` level, do not overwrite."""
    user_config = LoggingConfig(
        loggers={"_granian": {"level": "DEBUG", "handlers": ["console"], "propagate": False}}
    )
    env = _make_env(user_config)

    result = _get_logging_config(env, use_litestar_logger=True)

    assert result["loggers"]["_granian"]["level"] == "DEBUG"


def test_get_logging_config_no_litestar_logger_returns_deepcopy() -> None:
    """When use_litestar_logger is False, we still must not return the shared module dict."""
    env = _make_env(None)

    result = _get_logging_config(env, use_litestar_logger=False)
    result["formatters"]["generic"] = {"fmt": "mutated"}

    assert LOGGING_CONFIG["formatters"].get("generic", {}).get("fmt") != "mutated"


def test_neutralize_queue_handlers_linux_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 0 Task 0.2: Linux keeps queue handlers intact (fork workers re-configure fresh)."""
    monkeypatch.setattr("sys.platform", "linux")
    config = {
        "handlers": {
            "queue_listener": {
                "class": "litestar.logging.standard.QueueListenerHandler",
                "formatter": "standard",
                "level": "DEBUG",
            }
        }
    }
    original = copy.deepcopy(config)
    _neutralize_queue_handlers_for_platform(config)
    assert config == original


@pytest.mark.parametrize("platform_name", ["darwin", "win32"])
def test_neutralize_queue_handlers_spawn_platforms(
    monkeypatch: pytest.MonkeyPatch, platform_name: str
) -> None:
    """Phase 0 Task 0.2: spawn platforms swap QueueListenerHandler → StreamHandler."""
    monkeypatch.setattr("sys.platform", platform_name)
    config = {
        "handlers": {
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
        }
    }

    _neutralize_queue_handlers_for_platform(config)

    # Queue handler is now StreamHandler, original formatter/level preserved
    assert config["handlers"]["queue_listener"]["class"] == "logging.StreamHandler"
    assert config["handlers"]["queue_listener"]["formatter"] == "standard"
    assert config["handlers"]["queue_listener"]["level"] == "DEBUG"
    # Non-queue handler is untouched
    assert config["handlers"]["console"]["class"] == "logging.StreamHandler"
    assert config["handlers"]["console"]["level"] == "INFO"


def test_neutralize_queue_handlers_drops_listener_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Handlers with a ``listener`` key (Litestar 3.12+ style) lose the listener on spawn platforms."""
    monkeypatch.setattr("sys.platform", "darwin")
    config = {
        "handlers": {
            "queue": {
                "class": "logging.handlers.QueueHandler",
                "listener": "some.listener.factory",
                "formatter": "standard",
                "level": "INFO",
            }
        }
    }
    _neutralize_queue_handlers_for_platform(config)
    assert config["handlers"]["queue"]["class"] == "logging.StreamHandler"
    assert "listener" not in config["handlers"]["queue"]


def test_get_logging_config_platform_aware_on_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: on macOS, returned dictconfig has no QueueListenerHandler."""
    monkeypatch.setattr("sys.platform", "darwin")
    user_config = LoggingConfig(
        loggers={},
        handlers={
            "queue_listener": {
                "class": "litestar.logging.standard.QueueListenerHandler",
                "formatter": "standard",
                "level": "DEBUG",
            }
        },
    )
    env = _make_env(user_config)

    result = _get_logging_config(env, use_litestar_logger=True)

    for handler in result["handlers"].values():
        handler_class = handler.get("class") or handler.get("()")
        assert "QueueListenerHandler" not in str(handler_class)
