# The module name is part of the generated dictConfig import path.
# ruff: file-ignore[stdlib-module-shadowing]
"""Build child-owned Granian logging configurations from Litestar settings."""

import base64
import json
import logging
import logging.config
import pickle  # ruff: ignore[suspicious-pickle-import]
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, cast

from litestar.logging import LoggingConfig, StructLoggingConfig
from litestar.logging.config import BaseLoggingConfig

LogStyle = Literal["auto", "native", "standard", "json"]
ResolvedLogStyle = Literal["native", "standard", "json"]

_STANDARD_FORMAT = "%(levelname)s - %(asctime)s - %(name)s - %(module)s - %(message)s"
_SAFE_FORMATTER_FIELDS = ("format", "datefmt", "style")
_logger = logging.getLogger(__name__)


class _FormatterLike(Protocol):
    def format(self, record: logging.LogRecord) -> str: ...


class JSONFormatter(logging.Formatter):
    """Format Granian records as one process-safe JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:  # ruff: ignore[no-self-use]
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


def resolve_log_style(style: LogStyle, logging_config: object | None) -> ResolvedLogStyle:
    """Resolve ``auto`` from Litestar's configured logging substrate.

    Returns:
        The concrete Granian log presentation.
    """
    if style != "auto":
        return style
    if isinstance(logging_config, StructLoggingConfig):
        return "json"
    if isinstance(logging_config, LoggingConfig):
        return "standard"
    return "native"


def build_logging_config(
    style: ResolvedLogStyle,
    logging_config: BaseLoggingConfig | None = None,
) -> dict[str, Any] | None:
    """Build a JSON-serializable Granian dictConfig using direct streams.

    Returns:
        A process-safe dictConfig, or ``None`` for Granian-native logging.
    """
    if style == "native":
        return None

    if style == "json":
        generic_formatter = _structlog_formatter(logging_config) or {"()": "litestar_granian.logging.JSONFormatter"}
    else:
        generic_formatter = _standard_formatter(logging_config)
    access_formatter = dict(generic_formatter)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "generic": generic_formatter,
            "access": access_formatter,
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "generic",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "_granian": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": False,
            },
            "granian.access": {
                "handlers": ["access"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }


def load_serialized_formatter(payload: str) -> _FormatterLike:
    """Create a fresh child-owned formatter-compatible object.

    The payload is generated into a mode-600 temporary log configuration by
    this package. Only the formatter is transferred; handlers, queues,
    listeners, loggers, locks, and other live logging state remain isolated.
    The reconstructed object may be a standard formatter, a custom formatter,
    or another object that provides a callable ``format(record)`` method.

    Returns:
        A child-owned object with a callable ``format(record)`` method.

    Raises:
        TypeError: If the reconstructed object has no callable ``format``.
    """
    formatter = pickle.loads(base64.b64decode(payload.encode("ascii"), validate=True))  # ruff: ignore[suspicious-pickle-usage]
    if not callable(getattr(formatter, "format", None)):
        message = "Serialized Litestar formatter does not provide format()"
        raise TypeError(message)
    return cast("_FormatterLike", formatter)


def _standard_formatter(logging_config: BaseLoggingConfig | None) -> dict[str, str]:
    fallback = {"format": _STANDARD_FORMAT, "style": "%"}
    if not isinstance(logging_config, LoggingConfig):
        return fallback

    formatter = _active_formatter(logging_config)
    if not isinstance(formatter, dict):
        return fallback
    if "()" in formatter:
        return _serialized_formatter(formatter) or fallback
    selected = {key: value for key in _SAFE_FORMATTER_FIELDS if isinstance((value := formatter.get(key)), str)}
    return selected or fallback


def _structlog_formatter(logging_config: BaseLoggingConfig | None) -> dict[str, str] | None:
    if not isinstance(logging_config, StructLoggingConfig) or logging_config.standard_lib_logging_config is None:
        return None
    formatter = _active_formatter(logging_config.standard_lib_logging_config)
    return _serialized_formatter(formatter) if isinstance(formatter, dict) else None


def _serialized_formatter(formatter_config: dict[str, Any]) -> dict[str, str] | None:
    try:
        formatter = logging.config.DictConfigurator({"version": 1}).configure_formatter(deepcopy(formatter_config))
        payload = base64.b64encode(pickle.dumps(formatter, protocol=pickle.HIGHEST_PROTOCOL)).decode("ascii")
        load_serialized_formatter(payload)
    except Exception:  # ruff: ignore[blind-except]
        _logger.warning(
            "Unable to recreate Litestar's active formatter in the Granian child; using the built-in log preset."
        )
        return None
    return {
        "()": "litestar_granian.logging.load_serialized_formatter",
        "payload": payload,
    }


def _active_formatter(logging_config: LoggingConfig) -> dict[str, Any] | None:
    logger_config = logging_config.loggers.get("litestar", {})
    handler_names = logger_config.get("handlers") or logging_config.root.get("handlers") or ()
    pending = list(handler_names) if isinstance(handler_names, (list, tuple)) else [handler_names]
    visited: set[str] = set()
    while pending:
        handler_name = pending.pop(0)
        if not isinstance(handler_name, str) or handler_name in visited:
            continue
        visited.add(handler_name)
        handler = logging_config.handlers.get(handler_name)
        if not isinstance(handler, dict):
            continue
        formatter_name = handler.get("formatter")
        if isinstance(formatter_name, str):
            formatter = logging_config.formatters.get(formatter_name)
            if isinstance(formatter, dict):
                return formatter
        nested_handlers = handler.get("handlers") or ()
        if isinstance(nested_handlers, str):
            pending.append(nested_handlers)
        elif isinstance(nested_handlers, (list, tuple)):
            pending.extend(nested_handlers)
    return logging_config.formatters.get("standard")
