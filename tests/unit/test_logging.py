from __future__ import annotations

import json
import logging
import logging.config
import logging.handlers
import queue
import threading
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, cast

import pytest
from granian.log import LOGGING_CONFIG

from litestar_granian.logging import build_logging_config


class PrefixFormatter(logging.Formatter):
    """Importable formatter representative of an application's formatter."""

    def __init__(self, *, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def format(self, record: logging.LogRecord) -> str:
        return f"{self.prefix}::{record.levelname.lower()}::{record.getMessage()}"


class JSONFormatter(logging.Formatter):
    """User-defined JSON formatter with no production package dependency."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"level": record.levelname.lower(), "message": record.getMessage()}, sort_keys=True)


class SlottedFormatter(logging.Formatter):
    """User-defined formatter that stores presentation state in a slot."""

    __slots__ = ("prefix",)

    def __init__(self, *, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def format(self, record: logging.LogRecord) -> str:
        return f"{self.prefix}::{record.getMessage()}"


class AddApplicationFields:
    """Stateful structlog processor representative of an application processor."""

    def __init__(self, application: str) -> None:
        self.application = application

    def __call__(self, _: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict["application"] = self.application
        return event_dict


def _logger_with_handler(formatter: logging.Formatter) -> tuple[logging.Logger, logging.Handler]:
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger = _new_logger()
    logger.handlers = [handler]
    logger.propagate = False
    return logger, handler


def _new_logger() -> logging.Logger:
    return logging.getLoggerClass()("litestar")


def _configured_formatter(config: dict[str, Any]) -> logging.Formatter:
    return logging.config.DictConfigurator({"version": 1}).configure_formatter(deepcopy(config))


def _record() -> logging.LogRecord:
    return logging.LogRecord("_granian", logging.WARNING, __file__, 1, "served %s", ("request",), None)


def test_no_compatible_formatter_retains_granian_native_logging() -> None:
    logger = _new_logger()
    logger.propagate = False

    assert build_logging_config(None, logger=logger) is None


def test_direct_handler_formatter_replaces_only_granian_native_formatters() -> None:
    logger, _ = _logger_with_handler(PrefixFormatter(prefix="application"))
    native_config = deepcopy(LOGGING_CONFIG)

    config = build_logging_config(None, logger=logger)

    assert config is not None
    assert native_config == LOGGING_CONFIG
    assert config["handlers"] == native_config["handlers"]
    assert config["loggers"] == native_config["loggers"]
    assert set(config["formatters"]) == {"generic", "access"}
    assert config["formatters"]["generic"] == config["formatters"]["access"]
    assert _configured_formatter(config["formatters"]["generic"]).format(_record()) == (
        "application::warning::served request"
    )


def test_propagated_root_formatter_is_discovered() -> None:
    root_handler = logging.StreamHandler()
    root_handler.setFormatter(PrefixFormatter(prefix="root"))
    root = logging.RootLogger(logging.INFO)
    root.handlers = [root_handler]
    logger = _new_logger()
    logger.parent = root
    logger.propagate = True

    config = build_logging_config(None, logger=logger)

    assert config is not None
    assert _configured_formatter(config["formatters"]["generic"]).format(_record()) == "root::warning::served request"


def test_queue_listener_output_formatter_is_discovered_without_lifecycle_changes() -> None:
    formatter = PrefixFormatter(prefix="listener")
    output_handler = logging.StreamHandler()
    output_handler.setFormatter(formatter)
    queue_handler = logging.handlers.QueueHandler(queue.SimpleQueue())
    listener = logging.handlers.QueueListener(queue_handler.queue, output_handler)
    queue_handler.listener = listener
    logger = _new_logger()
    logger.handlers = [queue_handler]
    logger.propagate = False
    before_handlers = tuple(logger.handlers)
    before_threads = tuple(threading.enumerate())

    config = build_logging_config(None, logger=logger)

    assert config is not None
    assert tuple(logger.handlers) == before_handlers
    assert queue_handler.listener is listener
    assert listener._thread is None
    assert tuple(threading.enumerate()) == before_threads
    assert _configured_formatter(config["formatters"]["generic"]).format(_record()) == (
        "listener::warning::served request"
    )


def test_structurally_compatible_configuration_is_a_read_only_fallback() -> None:
    configured = SimpleNamespace(
        formatters={"custom": {"()": PrefixFormatter, "prefix": "configured"}},
        handlers={
            "queue": {"handlers": ["output"]},
            "output": {"formatter": "custom"},
        },
        loggers={"litestar": {"handlers": ["queue"], "propagate": False}},
        root={"handlers": []},
    )
    before = deepcopy(configured)
    logger = _new_logger()
    logger.propagate = False

    config = build_logging_config(configured, logger=logger)

    assert config is not None
    assert configured == before
    assert _configured_formatter(config["formatters"]["generic"]).format(_record()) == (
        "configured::warning::served request"
    )


def test_user_defined_json_formatter_is_recreated_automatically() -> None:
    logger, _ = _logger_with_handler(JSONFormatter())

    config = build_logging_config(None, logger=logger)

    assert config is not None
    assert json.loads(_configured_formatter(config["formatters"]["generic"]).format(_record())) == {
        "level": "warning",
        "message": "served request",
    }


def test_slotted_formatter_state_is_preserved_on_reconstruction() -> None:
    logger, _ = _logger_with_handler(SlottedFormatter(prefix="slotted"))

    config = build_logging_config(None, logger=logger)

    assert config is not None
    assert _configured_formatter(config["formatters"]["generic"]).format(_record()) == "slotted::served request"


def test_optional_structlog_formatter_is_recreated_without_production_classification() -> None:
    structlog = pytest.importorskip("structlog")
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            AddApplicationFields("example"),
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(sort_keys=True),
        ]
    )
    logger, _ = _logger_with_handler(formatter)

    config = build_logging_config(None, logger=logger)

    assert config is not None
    assert json.loads(_configured_formatter(config["formatters"]["generic"]).format(_record()))["application"] == (
        "example"
    )


def test_selected_formatter_reconstruction_failure_is_actionable() -> None:
    class LocalFormatter(logging.Formatter):
        pass

    logger, _ = _logger_with_handler(LocalFormatter())

    with pytest.raises(RuntimeError, match="--log-config"):
        build_logging_config(None, logger=logger)


def test_structlog_formatter_removes_dictconfig_live_state_on_serialization() -> None:
    structlog = pytest.importorskip("structlog")

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structlog": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer(sort_keys=True),
                ],
                "foreign_pre_chain": [
                    AddApplicationFields("example"),
                ],
            }
        },
        "handlers": {
            "queue": {
                "class": "logging.handlers.QueueHandler",
                "queue": queue.Queue(),
            },
            "output": {
                "class": "logging.StreamHandler",
                "formatter": "structlog",
            },
        },
        "loggers": {
            "litestar": {
                "handlers": ["queue"],
                "propagate": False,
            }
        },
    }

    try:
        logging.config.dictConfig(config)
        logger = logging.getLogger("litestar")

        queue_handler = cast("logging.handlers.QueueHandler", logger.handlers[0])
        logging_handlers = cast("dict[str, logging.Handler]", logging._handlers)  # pyright: ignore[reportAttributeAccessIssue]

        output_handler = logging_handlers["output"]
        listener = logging.handlers.QueueListener(queue_handler.queue, output_handler)
        setattr(queue_handler, "listener", listener)

        granian_config = build_logging_config(None, logger=logger)
        assert granian_config is not None

        payload = granian_config["formatters"]["generic"]["payload"]

        import base64
        import pickle  # ruff: ignore[suspicious-pickle-import]

        reconstructed = pickle.loads(base64.b64decode(payload.encode("ascii")))  # ruff: ignore[suspicious-pickle-usage]

        def _check_no_live_state(obj: Any, visited: set[int] | None = None) -> None:
            if visited is None:
                visited = set()
            if id(obj) in visited:
                return
            visited.add(id(obj))

            if isinstance(obj, list):
                assert type(obj) is list
                for item in obj:
                    _check_no_live_state(item, visited)
            elif isinstance(obj, dict):
                assert type(obj) is dict
                for v in obj.values():
                    _check_no_live_state(v, visited)

            type_name = type(obj).__name__
            assert type_name not in (
                "ConvertingList",
                "DictConfigurator",
                "QueueHandler",
                "QueueListener",
                "StreamHandler",
                "RLock",
            )

        _check_no_live_state(reconstructed.__dict__)
        assert json.loads(reconstructed.format(_record()))["application"] == "example"
    finally:
        handlers_dict = cast("dict[str, logging.Handler]", getattr(logging, "_handlers", {}))
        handlers_dict.pop("output", None)
        handlers_dict.pop("queue", None)
        logging.getLogger("litestar").handlers.clear()
