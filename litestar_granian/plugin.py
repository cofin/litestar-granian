from __future__ import annotations

from importlib.util import find_spec
from typing import TYPE_CHECKING

from litestar.logging.config import LoggingConfig
from litestar.plugins import CLIPluginProtocol, InitPluginProtocol

from litestar_granian.cli import run_command

if TYPE_CHECKING:
    from click import Group
    from litestar.config.app import AppConfig

STRUCTLOG_INSTALLED = find_spec("structlog") is not None


class GranianPlugin(InitPluginProtocol, CLIPluginProtocol):
    """Granian server plugin."""

    __slots__ = ()

    def on_cli_init(self, cli: Group) -> None:
        from litestar.cli.main import litestar_group as cli

        cli.add_command(run_command)
        return super().on_cli_init(cli)

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
            # this functionality only became available in litestar 2.6.  This conditional checks for this.
            for plugin in app_config.plugins:
                if (
                    plugin.__class__.__name__ == "StructlogPlugin"
                    and hasattr(plugin, "_config")
                    and (
                        plugin._config.structlog_logging_config.standard_lib_logging_config is not None  # noqa: SLF001
                        and plugin._config.structlog_logging_config.standard_lib_logging_config.loggers.get(  # noqa: SLF001
                            "_granian",
                            None,
                        )
                        is None
                    )
                ):
                    plugin._config.structlog_logging_config.standard_lib_logging_config.loggers.update(  # noqa: SLF001
                        {"_granian": {"level": "INFO", "handlers": ["queue_listener"], "propagate": False}},
                    )
                if (
                    plugin.__class__.__name__ == "StructlogPlugin"
                    and hasattr(plugin, "_config")
                    and (
                        plugin._config.structlog_logging_config.standard_lib_logging_config is not None  # noqa: SLF001
                        and plugin._config.structlog_logging_config.standard_lib_logging_config.formatters.get(  # noqa: SLF001
                            "standard",
                            None,
                        )
                        is None
                    )
                ):
                    plugin._config.structlog_logging_config.standard_lib_logging_config.formatters.update(  # noqa: SLF001
                        {"standard": {"format": "%(levelname)s - %(asctime)s - %(name)s - %(module)s - %(message)s"}},
                    )
        return super().on_app_init(app_config)
