from __future__ import annotations

from copy import deepcopy
from typing import Literal
from unittest.mock import MagicMock

import pytest
from click import Group
from litestar.config.app import AppConfig
from litestar.logging import LoggingConfig
from litestar.plugins import CLIPluginProtocol, InitPlugin

from litestar_granian.cli import run_command
from litestar_granian.plugin import GranianPlugin


def test_plugin_uses_current_litestar_base_classes() -> None:
    plugin = GranianPlugin()

    assert isinstance(plugin, InitPlugin)
    assert isinstance(plugin, CLIPluginProtocol)


def test_on_cli_init_registers_run_command_on_supplied_group() -> None:
    cli_group = Group()

    GranianPlugin().on_cli_init(cli_group)

    assert cli_group.commands["run"] is run_command


@pytest.mark.parametrize(
    "static",
    [
        "off",
        "auto",
    ],
)
def test_plugin_configuration(static: Literal["off", "auto"]) -> None:
    plugin = GranianPlugin(static=static)

    assert plugin.static == static


def test_plugin_rejects_invalid_static_configuration() -> None:
    with pytest.raises(ValueError):
        GranianPlugin(static="invalid")  # type: ignore[arg-type]


def test_on_app_init_does_not_mutate_or_eagerly_configure_logging() -> None:
    logging_config = LoggingConfig(loggers={})
    before = deepcopy(logging_config)
    logging_config.configure = MagicMock()  # type: ignore[method-assign]
    app_config = AppConfig(logging_config=logging_config)

    result = GranianPlugin().on_app_init(app_config)

    assert result is app_config
    assert logging_config.loggers == before.loggers
    logging_config.configure.assert_not_called()
