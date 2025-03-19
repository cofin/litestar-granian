from importlib.util import find_spec
from typing import TYPE_CHECKING, Optional

from litestar.plugins import CLIPluginProtocol, InitPluginProtocol
from typing_extensions import TypeGuard

if TYPE_CHECKING:
    try:
        from rich_click import Group
    except ImportError:
        from click import Group
    from litestar.config.app import AppConfig
    from litestar.logging.config import BaseLoggingConfig, LoggingConfig
    from litestar.plugins.structlog import StructlogPlugin

STRUCTLOG_INSTALLED = find_spec("structlog") is not None


class GranianPlugin(InitPluginProtocol, CLIPluginProtocol):
    """Granian server plugin."""

    __slots__ = ()

    def on_cli_init(self, cli: "Group") -> None:  # noqa: PLR6301
        from litestar.cli.main import litestar_group as cli

        from litestar_granian.cli import run_command

        cli.add_command(run_command)  # pyright: ignore[reportArgumentType]

    def on_app_init(self, app_config: "AppConfig") -> "AppConfig":
        if is_logging_config(app_config.logging_config):
            if app_config.logging_config.loggers.get("_granian", None) is None:
                app_config.logging_config.loggers.update({
                    "_granian": {"level": "INFO", "handlers": ["console"], "propagate": False},
                    "granian.access": {"level": "INFO", "handlers": ["console"], "propagate": False},
                })
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
            structlog_plugin = _get_structlog_plugin(app_config)
            if structlog_plugin is not None and is_logging_config(
                structlog_plugin._config.structlog_logging_config.standard_lib_logging_config
            ):
                structlog_plugin._config.structlog_logging_config.standard_lib_logging_config.loggers.update(
                    {
                        "_granian": {"level": "INFO", "handlers": ["console"], "propagate": False},
                        "granian.access": {"level": "INFO", "handlers": ["console"], "propagate": False},
                    },
                )
                if (
                    structlog_plugin._config.structlog_logging_config.standard_lib_logging_config.loggers.get(
                        "_granian", None
                    )
                    is None
                ):
                    structlog_plugin._config.structlog_logging_config.standard_lib_logging_config.loggers.update(
                        {
                            "_granian": {"level": "INFO", "handlers": ["console"], "propagate": False},
                            "granian.access": {"level": "INFO", "handlers": ["console"], "propagate": False},
                        },
                    )
                if (
                    structlog_plugin._config.structlog_logging_config.standard_lib_logging_config.formatters.get(
                        "standard",
                        None,
                    )
                    is None
                ):
                    structlog_plugin._config.structlog_logging_config.standard_lib_logging_config.formatters.update(
                        {"standard": {"format": "%(levelname)s - %(asctime)s - %(name)s - %(module)s - %(message)s"}},
                    )
                structlog_plugin._config.structlog_logging_config.configure()

        return super().on_app_init(app_config)


def _get_structlog_plugin(app_config: "AppConfig") -> "Optional[StructlogPlugin]":
    from litestar.plugins.structlog import StructlogPlugin

    for plugin in app_config.plugins:
        if isinstance(plugin, StructlogPlugin) and hasattr(plugin, "_config"):
            return plugin
    return None


def is_structlog_plugin(plugin: "InitPluginProtocol") -> TypeGuard["StructlogPlugin"]:
    from litestar.plugins.structlog import StructlogPlugin

    return isinstance(plugin, StructlogPlugin) and hasattr(plugin, "_config")


def is_logging_config(config: "Optional[BaseLoggingConfig]") -> TypeGuard["LoggingConfig"]:
    from litestar.logging.config import LoggingConfig

    return config is not None and isinstance(config, LoggingConfig)
