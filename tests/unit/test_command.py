from __future__ import annotations

import json
import logging
import multiprocessing
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click import UsageError
from granian.constants import HTTPModes, Loops
from granian.log import LogLevels
from litestar.logging import LoggingConfig

from litestar_granian import command
from litestar_granian.cli import _validate_cli_options, run_command
from litestar_granian.command import _build_granian_command
from litestar_granian.logging import build_logging_config
from litestar_granian.plugin import GranianPlugin


@pytest.fixture(autouse=True)
def _isolate_litestar_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = logging.getLoggerClass()("litestar")
    logger.propagate = False
    monkeypatch.setattr(command, "build_logging_config", lambda config: build_logging_config(config, logger=logger))


def _env(plugin: GranianPlugin | None = None, logging_config: object | None = None) -> Any:
    plugin = plugin or GranianPlugin()
    return SimpleNamespace(
        app_path="app:app",
        is_app_factory=False,
        app=SimpleNamespace(logging_config=logging_config, plugins=[plugin]),
    )


def _options(**overrides: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": 8000,
        "http": HTTPModes.auto,
        "wc": 1,
        "ws_enabled": True,
        "log_enabled": True,
        "log_level": LogLevels.info,
        "log_access_enabled": False,
        "http1_buffer_size": 417792,
        "http1_header_read_timeout": 30000,
        "http1_keep_alive": True,
        "http1_pipeline_flush": False,
        "http2_adaptive_window": False,
        "http2_initial_connection_window_size": 1048576,
        "http2_initial_stream_window_size": 1048576,
        "http2_keep_alive_interval": None,
        "http2_keep_alive_timeout": 20,
        "http2_max_concurrent_streams": 200,
        "http2_max_frame_size": 16384,
        "http2_max_headers_size": 16777216,
        "http2_max_send_buffer_size": 409600,
        "static_path_route": (),
        "static_path_mount": (),
        "static_path_dir_to_file": None,
        "static_path_expires": 86400,
        "log_config": None,
    }
    options.update(overrides)
    return options


def _argv(**overrides: Any) -> list[str]:
    built = _build_granian_command(_env(), _options(**overrides))
    try:
        return built.argv
    finally:
        built.cleanup()


def test_command_uses_current_interpreter_and_native_module() -> None:
    assert _argv()[:5] == [sys.executable, "-m", "granian", "app:app", "--interface=asgi"]


@pytest.mark.parametrize("loop", list(Loops))
def test_event_loop_values_are_forwarded_verbatim(loop: Loops) -> None:
    assert f"--loop={loop.value}" in _argv(loop=loop)


@pytest.mark.parametrize(
    ("http", "has_http1", "has_http2", "ws_flag"),
    [
        (HTTPModes.auto, True, True, "--ws"),
        (HTTPModes.http1, True, False, "--ws"),
        (HTTPModes.http2, False, True, "--no-ws"),
    ],
)
def test_http_mode_forwards_only_compatible_settings(
    http: HTTPModes,
    has_http1: bool,
    has_http2: bool,
    ws_flag: str,
) -> None:
    argv = _argv(http=http)

    assert any(arg.startswith("--http1-buffer-size=") for arg in argv) is has_http1
    assert any(arg.startswith("--http2-max-frame-size=") for arg in argv) is has_http2
    assert ws_flag in argv


def test_boolean_arguments_use_explicit_native_spellings() -> None:
    argv = _argv(
        log_enabled=False,
        http1_keep_alive=False,
        http1_pipeline_flush=True,
        log_access_enabled=True,
    )

    assert "--no-log" in argv
    assert "--no-http1-keep-alive" in argv
    assert "--http1-pipeline-flush" in argv
    assert "--access-log" in argv
    assert "--no-log-enabled" not in argv
    assert "--log-access-enabled" not in argv


def test_worker_lifecycle_and_runtime_options_are_forwarded(tmp_path: Path) -> None:
    pid_file = tmp_path / "granian.pid"
    argv = _argv(
        pid_file=pid_file,
        respawn_failed_workers=True,
        respawn_interval=7.5,
        blocking_threads=4,
        blocking_threads_idle_timeout=45,
        runtime_threads=3,
        runtime_blocking_threads=2,
        workers_lifetime=3600,
        workers_kill_timeout=5,
        workers_max_rss=512,
        rss_sample_interval=10,
        rss_samples=3,
    )

    assert f"--pid-file={pid_file.resolve()}" in argv
    assert "--respawn-failed-workers" in argv
    assert "--respawn-interval=7.5" in argv
    assert "--blocking-threads=4" in argv
    assert "--blocking-threads-idle-timeout=45" in argv
    assert "--runtime-threads=3" in argv
    assert "--runtime-blocking-threads=2" in argv
    assert "--workers-lifetime=3600" in argv
    assert "--workers-kill-timeout=5" in argv
    assert "--workers-max-rss=512" in argv
    assert "--rss-sample-interval=10" in argv
    assert "--rss-samples=3" in argv


def test_working_directory_env_files_metrics_and_uds_are_forwarded(tmp_path: Path) -> None:
    working_dir = tmp_path / "work"
    working_dir.mkdir()
    env_file = tmp_path / ".env"
    env_file.write_text("VALUE=1")
    uds = tmp_path / "granian.sock"

    argv = _argv(
        working_dir=working_dir,
        env_files=(env_file,),
        uds=uds,
        uds_permissions=0o660,
        metrics_enabled=True,
        metrics_scrape_interval=30,
        metrics_address="0.0.0.0",
        metrics_port=9191,
    )

    assert f"--working-dir={working_dir.resolve()}" in argv
    assert f"--env-files={env_file.resolve()}" in argv
    assert f"--uds={uds.resolve()}" in argv
    assert f"--uds-permissions={0o660}" in argv
    assert "--metrics" in argv
    assert "--metrics-scrape-interval=30" in argv
    assert "--metrics-address=0.0.0.0" in argv
    assert "--metrics-port=9191" in argv


def test_explicit_multi_mount_static_configuration_is_forwarded(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    argv = _argv(
        static_path_route=("/one", "/two"),
        static_path_mount=(first, second),
        static_path_dir_to_file="index.html",
        static_path_expires=0,
    )

    assert "--static-path-route=/one" in argv
    assert "--static-path-route=/two" in argv
    assert f"--static-path-mount={first.resolve()}" in argv
    assert f"--static-path-mount={second.resolve()}" in argv
    assert "--static-path-dir-to-file=index.html" in argv
    assert "--static-path-expires=0" in argv


def test_explicit_log_config_wins_completely(tmp_path: Path) -> None:
    config_path = tmp_path / "logging.json"
    config_path.write_text('{"version": 1}')

    built = _build_granian_command(
        _env(GranianPlugin(), LoggingConfig()),
        _options(log_config=config_path),
    )

    assert f"--log-config={config_path.resolve()}" in built.argv
    assert built.temporary_files == ()


def test_automatic_formatter_matching_generates_mode_600_config() -> None:
    built = _build_granian_command(_env(GranianPlugin(), LoggingConfig()), _options())
    try:
        (config_path,) = built.temporary_files
        payload = json.loads(config_path.read_text())
        assert payload["formatters"]["generic"]["()"] == "litestar_granian.logging.load_serialized_formatter"
        assert config_path.stat().st_mode & 0o777 == 0o600
    finally:
        built.cleanup()
    assert not config_path.exists()
    assert built.temporary_files == ()


def test_no_logging_config_keeps_granian_native_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = logging.getLogger("litestar")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "propagate", False)

    built = _build_granian_command(_env(GranianPlugin(), None), _options())

    assert not any(argument.startswith("--log-config=") for argument in built.argv)
    assert built.temporary_files == ()


def _validate(**overrides: Any) -> None:
    options: dict[str, Any] = {
        "fd": None,
        "reload": False,
        "workers_max_rss": None,
        "ssl_client_verify": False,
        "ssl_ca": None,
        "ssl_certificate": None,
        "ssl_keyfile": None,
        "create_self_signed_cert": False,
        "static_path_route": (),
        "static_path_mount": (),
    }
    options.update(overrides)
    _validate_cli_options(**options)


def test_ssl_client_verification_requires_ca() -> None:
    with pytest.raises(UsageError, match="--ssl-ca"):
        _validate(ssl_client_verify=True)


def test_static_route_and_mount_counts_must_match(tmp_path: Path) -> None:
    with pytest.raises(UsageError, match="counts"):
        _validate(static_path_route=("/one", "/two"), static_path_mount=(tmp_path,))


def test_certificate_authority_must_exist(tmp_path: Path) -> None:
    missing = tmp_path / "ca.pem"

    with pytest.raises(UsageError, match=f"File provided for --ssl-ca was not found: {missing.resolve()}"):
        _validate(ssl_client_verify=True, ssl_ca=missing)


@pytest.mark.parametrize(
    ("provided", "missing_option"),
    [("ssl_certificate", "--ssl-keyfile"), ("ssl_keyfile", "--ssl-certfile")],
)
def test_certificate_and_key_must_be_provided_together(
    tmp_path: Path,
    provided: str,
    missing_option: str,
) -> None:
    path = tmp_path / "provided.pem"
    path.write_text("value")

    with pytest.raises(UsageError, match=f"No value provided for {missing_option}"):
        _validate(**{provided: path})


def test_certificate_and_key_must_exist_without_self_signed_generation(tmp_path: Path) -> None:
    certificate = tmp_path / "cert.pem"
    keyfile = tmp_path / "key.pem"
    certificate.write_text("certificate")

    with pytest.raises(UsageError, match=f"File provided for --ssl-keyfile was not found: {keyfile.resolve()}"):
        _validate(ssl_certificate=certificate, ssl_keyfile=keyfile)


def test_certificate_path_must_not_be_a_directory(tmp_path: Path) -> None:
    keyfile = tmp_path / "key.pem"
    keyfile.write_text("key")

    with pytest.raises(UsageError, match=f"Path provided for --ssl-certfile is a directory: {tmp_path.resolve()}"):
        _validate(ssl_certificate=tmp_path, ssl_keyfile=keyfile)


def test_self_signed_generation_skips_existence_checks(tmp_path: Path) -> None:
    _validate(
        ssl_certificate=tmp_path / "cert.pem",
        ssl_keyfile=tmp_path / "key.pem",
        create_self_signed_cert=True,
    )


def test_existing_certificate_and_key_pass_validation(tmp_path: Path) -> None:
    certificate = tmp_path / "cert.pem"
    keyfile = tmp_path / "key.pem"
    certificate.write_text("certificate")
    keyfile.write_text("key")

    _validate(ssl_certificate=certificate, ssl_keyfile=keyfile)


def test_v016_help_preserves_litestar_and_deprecated_compatibility_options() -> None:
    option_names = {
        option
        for parameter in run_command.params
        for option in (*parameter.opts, *getattr(parameter, "secondary_opts", ()))
    }

    assert "--in-subprocess" in option_names
    assert "--no-subprocess" in option_names
    assert "--use-litestar-logger" in option_names
    assert "--no-litestar-logger" in option_names
    assert "--reload-include" in option_names
    assert "--reload-exclude" in option_names
    assert "-I" in option_names
    assert "-E" in option_names
    assert "-F" in option_names
    assert "--fd" in option_names
    assert "--file-descriptor" in option_names
    assert "-R" in option_names
    assert "--reload-dir" in option_names
    assert "--reload-paths" in option_names
    assert "-U" in option_names
    assert "--unix-domain-socket" in option_names
    assert "--uds" in option_names


def test_litestar_reload_filters_use_compatibility_runner() -> None:
    built = _build_granian_command(
        _env(),
        _options(reload=True, reload_include=("*.html",), reload_exclude=("*.tmp",)),
    )

    assert built.argv[:4] == [sys.executable, "-m", "litestar_granian._runner", "app:app"]
    assert json.loads(built.environment["LITESTAR_GRANIAN_RELOAD_INCLUDES"]) == ["*.html"]
    assert json.loads(built.environment["LITESTAR_GRANIAN_RELOAD_EXCLUDES"]) == ["*.tmp"]


@pytest.mark.skipif(sys.platform == "win32", reason="inherited file descriptors are POSIX-only")
def test_litestar_file_descriptor_uses_compatibility_runner() -> None:
    built = _build_granian_command(_env(), _options(fd=7))

    assert built.argv[:4] == [sys.executable, "-m", "litestar_granian._runner", "app:app"]
    assert built.environment["LITESTAR_GRANIAN_FILE_DESCRIPTOR"] == "7"
    assert built.pass_fds == (7,)


def test_worker_count_has_no_cpu_based_maximum() -> None:
    workers = next(parameter for parameter in run_command.params if parameter.name == "wc")
    workers_type: Any = workers.type

    assert workers_type.min == 1
    assert workers_type.max is None


@pytest.mark.parametrize(
    ("name", "minimum", "maximum"),
    [
        ("http2_initial_connection_window_size", 1024, None),
        ("http2_initial_stream_window_size", 1024, None),
        ("http2_keep_alive_interval", 1, 60000),
        ("http2_max_concurrent_streams", 10, None),
        ("http2_max_frame_size", 1024, None),
        ("http2_max_headers_size", 1, None),
        ("http2_max_send_buffer_size", 1024, None),
    ],
)
def test_http2_ranges_match_granian_279(name: str, minimum: int, maximum: int | None) -> None:
    parameter = next(parameter for parameter in run_command.params if parameter.name == name)
    parameter_type: Any = parameter.type

    assert parameter_type.min == minimum
    assert parameter_type.max == maximum


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("host", ["LITESTAR_HOST", "GRANIAN_HOST"]),
        ("port", ["LITESTAR_PORT", "GRANIAN_PORT"]),
        ("uds", ["LITESTAR_UNIX_DOMAIN_SOCKET", "GRANIAN_UDS"]),
        (
            "wc",
            ["LITESTAR_WEB_CONCURRENCY", "WEB_CONCURRENCY", "GRANIAN_WORKERS"],
        ),
        ("reload", ["LITESTAR_RELOAD", "GRANIAN_RELOAD"]),
        ("reload_paths", ["LITESTAR_RELOAD_DIRS", "GRANIAN_RELOAD_PATHS"]),
        (
            "ssl_certificate",
            ["LITESTAR_SSL_CERT_PATH", "GRANIAN_SSL_CERTIFICATE"],
        ),
        ("ssl_keyfile", ["LITESTAR_SSL_KEY_PATH", "GRANIAN_SSL_KEYFILE"]),
        (
            "ssl_client_verify",
            ["LITESTAR_SSL_CLIENT_VERIFY", "GRANIAN_SSL_CLIENT_VERIFY"],
        ),
    ],
)
def test_litestar_environment_precedes_granian_environment(name: str, expected: list[str]) -> None:
    parameter = next(parameter for parameter in run_command.params if parameter.name == name)

    assert parameter.envvar == expected


@pytest.mark.parametrize("name", ["reload_paths", "reload_include", "reload_exclude"])
def test_litestar_reload_environment_values_are_comma_separated(name: str) -> None:
    parameter = next(parameter for parameter in run_command.params if parameter.name == name)

    assert parameter.type.envvar_list_splitter == ","


def test_every_native_option_exposes_a_granian_environment_source() -> None:
    litestar_only = {"debug", "pdb", "create_self_signed_cert"}

    for parameter in run_command.params:
        if parameter.name in litestar_only:
            continue
        envvars = [parameter.envvar] if isinstance(parameter.envvar, str) else list(parameter.envvar or ())
        assert any(envvar.startswith("GRANIAN_") for envvar in envvars), parameter.name


def test_reload_does_not_mutate_global_multiprocessing_state() -> None:
    original = multiprocessing.get_start_method(allow_none=True)

    argv = _argv(reload=True)

    assert "--reload" in argv
    assert multiprocessing.get_start_method(allow_none=True) == original
