from __future__ import annotations

import json
import logging
import logging.config
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import structlog
from litestar.logging import LoggingConfig, StructLoggingConfig

from litestar_granian.logging import JSONFormatter, ResolvedLogStyle, build_logging_config, resolve_log_style


class CustomFormatter(logging.Formatter):
    """Importable formatter representative of an application's formatter."""

    def __init__(self, *, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def format(self, record: logging.LogRecord) -> str:
        return f"{self.prefix}::{record.levelname.lower()}::{record.getMessage()}"


class AddApplicationFields:
    """Stateful structlog processor representative of an application processor."""

    def __init__(self, application: str) -> None:
        self.application = application

    def __call__(self, _: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict["application"] = self.application
        return event_dict


def _configured_formatter(config: dict[str, Any]) -> logging.Formatter:
    return logging.config.DictConfigurator({"version": 1}).configure_formatter(deepcopy(config))


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (None, "native"),
        (LoggingConfig(), "standard"),
        (StructLoggingConfig(), "json"),
    ],
)
def test_auto_log_style_matches_litestar_configuration(configured: object, expected: str) -> None:
    assert resolve_log_style("auto", configured) == expected


def test_explicit_log_style_wins() -> None:
    assert resolve_log_style("native", StructLoggingConfig()) == "native"


def test_native_style_does_not_generate_a_config() -> None:
    assert build_logging_config("native") is None


@pytest.mark.parametrize("style", ["standard", "json"])
def test_generated_configs_use_only_direct_stdout_handlers(style: ResolvedLogStyle) -> None:
    config = build_logging_config(style)

    assert config is not None
    assert json.loads(json.dumps(config)) == config
    assert set(config["loggers"]) == {"_granian", "granian.access"}
    for handler in config["handlers"].values():
        assert handler["class"] == "logging.StreamHandler"
        assert handler["stream"] == "ext://sys.stdout"
        assert "queue" not in str(handler).lower()
        assert "listener" not in str(handler).lower()


def test_standard_style_copies_only_safe_scalar_formatter_fields() -> None:
    configured = LoggingConfig(
        formatters={
            "standard": {
                "format": "%(levelname)s %(message)s",
                "datefmt": "%H:%M:%S",
                "style": "%",
                "validate": False,
            }
        }
    )

    config = build_logging_config("standard", configured)

    assert config is not None
    assert config["formatters"]["generic"] == {
        "format": "%(levelname)s %(message)s",
        "datefmt": "%H:%M:%S",
        "style": "%",
    }


@pytest.mark.parametrize(
    ("format_string", "style"),
    [
        ("[%(name)s] %(levelname)s :: %(message)s", "%"),
        ("[{name}] {levelname} :: {message}", "{"),
        ("[$name] $levelname :: $message", "$"),
    ],
)
def test_standard_style_follows_the_formatter_on_litestar_active_handler_chain(
    format_string: str,
    style: str,
) -> None:
    configured = LoggingConfig(
        formatters={
            "custom": {
                "format": format_string,
                "datefmt": "%H:%M",
                "style": style,
            }
        },
        handlers={
            "custom_console": {
                "class": "logging.StreamHandler",
                "formatter": "custom",
            },
            "queue_listener": {
                "class": "logging.handlers.QueueHandler",
                "handlers": ["custom_console"],
            },
        },
        loggers={
            "litestar": {
                "level": "INFO",
                "handlers": ["queue_listener"],
                "propagate": False,
            }
        },
    )
    before = deepcopy(configured)
    record = logging.LogRecord("litestar", logging.INFO, __file__, 1, "served %s", ("request",), None)

    config = build_logging_config("standard", configured)

    assert config is not None
    selected = config["formatters"]["generic"]
    litestar_formatter = logging.Formatter(
        fmt=configured.formatters["custom"]["format"],
        datefmt=configured.formatters["custom"]["datefmt"],
        style=configured.formatters["custom"]["style"],
    )
    granian_formatter = logging.Formatter(
        fmt=selected["format"],
        datefmt=selected["datefmt"],
        style=selected["style"],
    )
    assert granian_formatter.format(record) == litestar_formatter.format(record)
    assert configured == before


def test_builtin_standard_preset_matches_litestar_default_shape() -> None:
    config = build_logging_config("standard")

    assert config is not None
    assert config["formatters"]["generic"]["format"] == LoggingConfig().formatters["standard"]["format"]


def test_callable_formatter_is_recreated_with_the_same_output() -> None:
    configured = LoggingConfig(
        formatters={"custom": {"()": CustomFormatter, "prefix": "application"}},
        handlers={"custom_console": {"class": "logging.StreamHandler", "formatter": "custom"}},
        loggers={"litestar": {"level": "INFO", "handlers": ["custom_console"], "propagate": False}},
    )
    record = logging.LogRecord("_granian", logging.WARNING, __file__, 1, "served %s", ("request",), None)

    config = build_logging_config("standard", configured)

    assert config is not None
    assert json.loads(json.dumps(config)) == config
    expected = _configured_formatter(configured.formatters["custom"])
    actual = _configured_formatter(config["formatters"]["generic"])
    assert actual.format(record) == expected.format(record)


def test_callable_formatter_is_recreated_in_a_fresh_process(tmp_path: Path) -> None:
    configured = LoggingConfig(
        formatters={"custom": {"()": CustomFormatter, "prefix": "application"}},
        handlers={"custom_console": {"class": "logging.StreamHandler", "formatter": "custom"}},
        loggers={"litestar": {"level": "INFO", "handlers": ["custom_console"], "propagate": False}},
    )
    config = build_logging_config("standard", configured)
    assert config is not None
    config_path = tmp_path / "logging.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    script = """
import json
import logging
import logging.config
import sys

with open(sys.argv[1], encoding="utf-8") as config_file:
    logging.config.dictConfig(json.load(config_file))
logging.getLogger("_granian").warning("served %s", "request")
"""

    completed = subprocess.run(
        [sys.executable, "-c", script, str(config_path)],
        check=True,
        capture_output=True,
        cwd=Path(__file__).parents[1],
        text=True,
    )

    assert completed.stdout.strip() == "application::warning::served request"


def test_structlog_processor_formatter_is_recreated_with_the_same_output() -> None:
    standard_logging = LoggingConfig(
        formatters={
            "custom": {
                "()": "structlog.stdlib.ProcessorFormatter",
                "processors": [
                    AddApplicationFields("example"),
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer(sort_keys=True),
                ],
            }
        },
        handlers={"custom_console": {"class": "logging.StreamHandler", "formatter": "custom"}},
        loggers={"litestar": {"level": "INFO", "handlers": ["custom_console"], "propagate": False}},
    )
    configured = StructLoggingConfig(standard_lib_logging_config=standard_logging)
    record = logging.LogRecord("_granian", logging.INFO, __file__, 1, "served %s", ("request",), None)

    config = build_logging_config("json", configured)

    assert config is not None
    assert json.loads(json.dumps(config)) == config
    expected = _configured_formatter(standard_logging.formatters["custom"])
    actual = _configured_formatter(config["formatters"]["generic"])
    assert json.loads(actual.format(record)) == json.loads(expected.format(record))


def test_non_transferable_formatter_uses_builtin_standard_preset(caplog: pytest.LogCaptureFixture) -> None:
    class LocalFormatter(logging.Formatter):
        pass

    configured = LoggingConfig(formatters={"standard": {"()": LocalFormatter}})

    with caplog.at_level(logging.WARNING, logger="litestar_granian.logging"):
        config = build_logging_config("standard", configured)

    assert config is not None
    assert config["formatters"]["generic"]["format"] == LoggingConfig().formatters["standard"]["format"]
    assert "Unable to recreate Litestar's active formatter" in caplog.text


def test_json_formatter_emits_stable_process_safe_shape() -> None:
    record = logging.LogRecord("granian.access", logging.INFO, __file__, 1, "served %s", ("request",), None)

    payload = json.loads(JSONFormatter().format(record))

    assert payload["level"] == "info"
    assert payload["logger"] == "granian.access"
    assert payload["event"] == "served request"
    assert payload["timestamp"].endswith("Z")
