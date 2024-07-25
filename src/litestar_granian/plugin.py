from __future__ import annotations

from importlib.util import find_spec
from typing import TYPE_CHECKING

from litestar.logging.config import LoggingConfig
from litestar.plugins import CLIPluginProtocol, InitPluginProtocol

from litestar_granian.cli import run_command

try:
    # this functionality only became available in litestar 2.6.
    from litestar.plugins.structlog import StructlogPlugin
except ImportError:  # pragma: nocover

    class StructlogPlugin:  # type: ignore[no-redef] # pragma: nocover
        """Fallback implementation for compatibility."""


if TYPE_CHECKING:
    from click import Group
    from litestar.config.app import AppConfig

STRUCTLOG_INSTALLED = find_spec("structlog") is not None


class GranianPlugin(InitPluginProtocol, CLIPluginProtocol):
    """Granian server plugin."""

    __slots__ = ()

    def on_cli_init(self, cli: Group) -> None:  # noqa: PLR6301
        from litestar.cli.main import litestar_group as cli  # noqa: PLC0415

        cli.add_command(run_command)

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        if app_config.logging_config is not None and isinstance(app_config.logging_config, LoggingConfig):
            if app_config.logging_config.loggers.get("_granian", None) is None:
                app_config.logging_config.loggers.update(
                    {"_granian": {"level": "INFO", "handlers": ["queue_listener"], "propagate": False}},
                )
            if app_config.logging_config.formatters.get("generic", None) is None:
                app_config.logging_config.formatters.update(
                    {
                        "generic": app_config.logging_config.formatters.get(
                            "standard",
                            {"format": "%(levelname)s - %(asctime)s - %(name)s - %(module)s - %(message)s"},
                        ),
                    },
                )
            app_config.logging_config.configure()
        if STRUCTLOG_INSTALLED:
            for plugin in app_config.plugins:
                if (
                    isinstance(plugin, StructlogPlugin)
                    and hasattr(plugin, "_config")
                    and (
                        plugin._config.structlog_logging_config.standard_lib_logging_config is not None
                        and plugin._config.structlog_logging_config.standard_lib_logging_config.loggers.get(
                            "_granian",
                            None,
                        )
                        is None
                    )
                ):
                    plugin._config.structlog_logging_config.standard_lib_logging_config.loggers.update(
                        {"_granian": {"level": "INFO", "handlers": ["queue_listener"], "propagate": False}},
                    )
                if (
                    isinstance(plugin, StructlogPlugin)
                    and hasattr(plugin, "_config")
                    and (
                        plugin._config.structlog_logging_config.standard_lib_logging_config is not None
                        and plugin._config.structlog_logging_config.standard_lib_logging_config.formatters.get(
                            "standard",
                            None,
                        )
                        is None
                    )
                ):
                    plugin._config.structlog_logging_config.standard_lib_logging_config.formatters.update(
                        {"standard": {"format": "%(levelname)s - %(asctime)s - %(name)s - %(module)s - %(message)s"}},
                    )
                plugin._config.structlog_logging_config.configure()  # type: ignore[union-attr]

        return super().on_app_init(app_config)
