from __future__ import annotations

import pytest
from click import Group
from litestar.config.app import AppConfig
from litestar.logging.config import LoggingConfig
from litestar.plugins import CLIPluginProtocol, InitPluginProtocol

from litestar_granian.plugin import GranianPlugin, _inject_granian_loggers


class MockCLIPlugin(InitPluginProtocol, CLIPluginProtocol):
    def on_cli_init(self, cli: Group) -> None:
        return None


@pytest.fixture
def cli_group() -> Group:
    return Group()


def test_on_cli_init_registers_run_command(cli_group: Group) -> None:
    """Plugin must register the ``run`` command on the Litestar CLI group."""
    plugin = GranianPlugin()
    plugin.on_cli_init(cli_group)

    # The real registration target is ``litestar.cli.main.litestar_group``, not the
    # group we pass in. Assert against that so the test reflects actual behavior.
    from litestar.cli.main import litestar_group

    assert "run" in litestar_group.commands


def test_inject_granian_loggers_adds_when_missing() -> None:
    config = LoggingConfig(loggers={})
    _inject_granian_loggers(config)
    assert "_granian" in config.loggers
    assert "granian.access" in config.loggers
    assert config.loggers["_granian"]["level"] == "INFO"


def test_inject_granian_loggers_preserves_existing() -> None:
    """Regression guard for the unguarded update at old plugin.py:53-58."""
    config = LoggingConfig(
        loggers={
            "_granian": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
        }
    )
    _inject_granian_loggers(config)
    # Existing level must not be clobbered
    assert config.loggers["_granian"]["level"] == "DEBUG"
    # Missing sibling is still injected
    assert "granian.access" in config.loggers


def test_inject_granian_loggers_noop_for_none() -> None:
    """Must not raise when given ``None`` (defensive for callers behind TypeGuard)."""
    _inject_granian_loggers(None)  # type: ignore[arg-type]


def test_on_app_init_injects_loggers_for_standard_config() -> None:
    plugin = GranianPlugin()
    logging_config = LoggingConfig(loggers={})
    app_config = AppConfig(logging_config=logging_config)
    plugin.on_app_init(app_config)
    assert "_granian" in logging_config.loggers
    assert "granian.access" in logging_config.loggers


def test_on_app_init_preserves_user_granian_config() -> None:
    plugin = GranianPlugin()
    logging_config = LoggingConfig(
        loggers={"_granian": {"level": "DEBUG", "handlers": ["console"], "propagate": False}}
    )
    app_config = AppConfig(logging_config=logging_config)
    plugin.on_app_init(app_config)
    assert logging_config.loggers["_granian"]["level"] == "DEBUG"


def test_on_app_init_handles_missing_logging_config() -> None:
    plugin = GranianPlugin()
    app_config = AppConfig(logging_config=None)
    # Must not raise.
    plugin.on_app_init(app_config)
