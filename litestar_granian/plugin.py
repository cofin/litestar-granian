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

_GRANIAN_LOGGER_CONFIG = {"level": "INFO", "handlers": ["console"], "propagate": False}
_DEFAULT_FORMATTER_FMT = "%(levelname)s - %(asctime)s - %(name)s - %(module)s - %(message)s"


def _inject_granian_loggers(logging_config: "Optional[LoggingConfig]") -> None:
    """Inject ``_granian`` / ``granian.access`` loggers into a logging config, non-destructively.

    Mirrors the guard pattern used for the non-structlog path: only adds a logger
    entry when the key is missing. Existing user-defined entries are preserved.
    """
    if logging_config is None:
        return
    if logging_config.loggers.get("_granian") is None:
        logging_config.loggers["_granian"] = dict(_GRANIAN_LOGGER_CONFIG)
    if logging_config.loggers.get("granian.access") is None:
        logging_config.loggers["granian.access"] = dict(_GRANIAN_LOGGER_CONFIG)


def _ensure_generic_formatter(logging_config: "Optional[LoggingConfig]", fallback_key: str = "standard") -> None:
    """Ensure a ``generic`` formatter exists so Granian's default config finds one."""
    if logging_config is None:
        return
    if logging_config.formatters.get("generic") is None:
        logging_config.formatters["generic"] = logging_config.formatters.get(
            fallback_key, {"format": _DEFAULT_FORMATTER_FMT}
        )


class GranianPlugin(InitPluginProtocol, CLIPluginProtocol):
    """Granian server plugin."""

    __slots__ = ()

    def on_cli_init(self, cli: "Group") -> None:  # noqa: PLR6301
        from litestar.cli.main import litestar_group as cli

        from litestar_granian.cli import run_command

        cli.add_command(run_command)  # pyright: ignore[reportArgumentType]

    def on_app_init(self, app_config: "AppConfig") -> "AppConfig":
        if is_logging_config(app_config.logging_config):
            _inject_granian_loggers(app_config.logging_config)
            _ensure_generic_formatter(app_config.logging_config)
            app_config.logging_config.configure()
        if STRUCTLOG_INSTALLED:
            structlog_plugin = _get_structlog_plugin(app_config)
            if structlog_plugin is not None and is_logging_config(
                structlog_plugin._config.structlog_logging_config.standard_lib_logging_config
            ):
                stdlib_config = structlog_plugin._config.structlog_logging_config.standard_lib_logging_config
                _inject_granian_loggers(stdlib_config)
                if stdlib_config.formatters.get("standard") is None:
                    stdlib_config.formatters["standard"] = {"format": _DEFAULT_FORMATTER_FMT}
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
