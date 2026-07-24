"""Translate Litestar-facing options into one native Granian child command."""

import json
import os
import sys
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from litestar_granian.logging import build_logging_config, resolve_log_style
from litestar_granian.plugin import GranianPlugin, LogStyle
from litestar_granian.static import _resolve_static_mounts

if TYPE_CHECKING:
    from litestar.cli._utils import LitestarEnv


@dataclass
class _BuiltCommand:
    argv: list[str]
    temporary_files: tuple[Path, ...] = ()
    environment: dict[str, str] = field(default_factory=dict)
    pass_fds: tuple[int, ...] = ()

    def cleanup(self) -> None:
        for path in self.temporary_files:
            path.unlink(missing_ok=True)


def _build_granian_command(env: "LitestarEnv", options: Mapping[str, Any]) -> _BuiltCommand:
    """Build one native Granian command from the Litestar-facing options.

    Returns:
        A command and any temporary files that must be cleaned up after use.
    """
    runner_module, environment, pass_fds = _compatibility_process(options)
    argv = [sys.executable, "-m", runner_module, env.app_path, "--interface=asgi"]

    _add_value(argv, "host", options.get("host"))
    _add_value(argv, "port", options.get("port"))
    _add_value(argv, "uds", options.get("uds"), absolute_path=True)
    _add_value(argv, "uds-permissions", options.get("uds_permissions"))
    _add_value(argv, "http", options.get("http"))
    _add_value(argv, "workers", options.get("wc"))
    _add_value(argv, "blocking-threads", options.get("blocking_threads"))
    _add_value(argv, "blocking-threads-idle-timeout", options.get("blocking_threads_idle_timeout"))
    _add_value(argv, "runtime-threads", options.get("runtime_threads"))
    _add_value(argv, "runtime-blocking-threads", options.get("runtime_blocking_threads"))
    _add_value(argv, "runtime-mode", options.get("runtime_mode"))
    _add_value(argv, "loop", options.get("loop"))
    _add_value(argv, "task-impl", options.get("task_impl"))
    _add_value(argv, "backlog", options.get("backlog"))
    _add_value(argv, "backpressure", options.get("backpressure"))

    http_value = _value(options.get("http"))
    if http_value in {"auto", "1"}:
        _add_value(argv, "http1-buffer-size", options.get("http1_buffer_size"))
        _add_value(argv, "http1-header-read-timeout", options.get("http1_header_read_timeout"))
        _add_bool(argv, "http1-keep-alive", options.get("http1_keep_alive"))
        _add_bool(argv, "http1-pipeline-flush", options.get("http1_pipeline_flush"))
    if http_value in {"auto", "2"}:
        _add_bool(argv, "http2-adaptive-window", options.get("http2_adaptive_window"))
        _add_value(
            argv,
            "http2-initial-connection-window-size",
            options.get("http2_initial_connection_window_size"),
        )
        _add_value(argv, "http2-initial-stream-window-size", options.get("http2_initial_stream_window_size"))
        _add_value(argv, "http2-keep-alive-interval", options.get("http2_keep_alive_interval"))
        _add_value(argv, "http2-keep-alive-timeout", options.get("http2_keep_alive_timeout"))
        _add_value(argv, "http2-max-concurrent-streams", options.get("http2_max_concurrent_streams"))
        _add_value(argv, "http2-max-frame-size", options.get("http2_max_frame_size"))
        _add_value(argv, "http2-max-headers-size", options.get("http2_max_headers_size"))
        _add_value(argv, "http2-max-send-buffer-size", options.get("http2_max_send_buffer_size"))
    _add_bool(argv, "ws", False if http_value == "2" else options.get("ws_enabled"))

    _add_bool(argv, "log", options.get("log_enabled"))
    _add_value(argv, "log-level", options.get("log_level"))
    _add_bool(argv, "access-log", options.get("log_access_enabled"))
    _add_value(argv, "access-log-fmt", options.get("log_access_fmt"))
    _add_value(argv, "ssl-certificate", options.get("ssl_certificate"), absolute_path=True)
    _add_value(argv, "ssl-keyfile", options.get("ssl_keyfile"), absolute_path=True)
    _add_value(argv, "ssl-keyfile-password", options.get("ssl_keyfile_password"))
    _add_value(argv, "ssl-protocol-min", options.get("ssl_protocol_min"))
    _add_value(argv, "ssl-ca", options.get("ssl_ca"), absolute_path=True)
    _add_repeated(argv, "ssl-crl", options.get("ssl_crl"), absolute_path=True)
    _add_bool(argv, "ssl-client-verify", options.get("ssl_client_verify"))
    _add_value(argv, "url-path-prefix", options.get("url_path_prefix"))

    _add_bool(argv, "respawn-failed-workers", options.get("respawn_failed_workers"))
    _add_value(argv, "respawn-interval", options.get("respawn_interval"))
    _add_value(argv, "workers-lifetime", options.get("workers_lifetime"))
    _add_value(argv, "workers-kill-timeout", options.get("workers_kill_timeout"))
    _add_value(argv, "workers-max-rss", options.get("workers_max_rss"))
    _add_value(argv, "rss-sample-interval", options.get("rss_sample_interval"))
    _add_value(argv, "rss-samples", options.get("rss_samples"))
    _add_bool(argv, "factory", env.is_app_factory)

    _add_value(argv, "working-dir", options.get("working_dir"), absolute_path=True)
    _add_repeated(argv, "env-files", options.get("env_files"), absolute_path=True)
    _add_bool(argv, "reload", options.get("reload"))
    _add_repeated(argv, "reload-paths", options.get("reload_paths"), absolute_path=True)
    _add_repeated(argv, "reload-ignore-dirs", options.get("reload_ignore_dirs"))
    _add_repeated(argv, "reload-ignore-patterns", options.get("reload_ignore_patterns"))
    _add_repeated(argv, "reload-ignore-paths", options.get("reload_ignore_paths"), absolute_path=True)
    _add_value(argv, "reload-tick", options.get("reload_tick"))
    _add_bool(argv, "reload-ignore-worker-failure", options.get("reload_ignore_worker_failure"))
    _add_value(argv, "process-name", options.get("process_name"))
    _add_value(argv, "pid-file", options.get("pid_file"), absolute_path=True)

    _add_bool(argv, "metrics", options.get("metrics_enabled"))
    if options.get("metrics_enabled"):
        _add_value(argv, "metrics-scrape-interval", options.get("metrics_scrape_interval"))
        _add_value(argv, "metrics-address", options.get("metrics_address"))
        _add_value(argv, "metrics-port", options.get("metrics_port"))

    plugin = _get_plugin(env)
    static_config = _resolve_static_mounts(
        env.app,
        static_mode=plugin.static,
        explicit_routes=tuple(options.get("static_path_route") or ()),
        explicit_mounts=tuple(options.get("static_path_mount") or ()),
        explicit_directory_index=options.get("static_path_dir_to_file"),
    )
    if static_config is not None:
        _add_repeated(argv, "static-path-route", static_config.routes)
        _add_repeated(argv, "static-path-mount", static_config.mounts, absolute_path=True)
        _add_value(argv, "static-path-dir-to-file", static_config.directory_index)
        _add_value(argv, "static-path-expires", options.get("static_path_expires"))

    explicit_log_config = options.get("log_config")
    if explicit_log_config is not None:
        _add_value(argv, "log-config", explicit_log_config, absolute_path=True)
        return _BuiltCommand(argv, environment=environment, pass_fds=pass_fds)

    requested_style = cast("LogStyle", options.get("granian_log_style") or plugin.log_style)
    resolved_style = resolve_log_style(requested_style, env.app.logging_config)
    log_config = build_logging_config(resolved_style, env.app.logging_config)
    if log_config is None:
        return _BuiltCommand(argv, environment=environment, pass_fds=pass_fds)

    fd, raw_path = tempfile.mkstemp(prefix="litestar-granian-", suffix=".json")
    config_path = Path(raw_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as config_file:
            json.dump(log_config, config_file)
    except Exception:
        config_path.unlink(missing_ok=True)
        raise
    _add_value(argv, "log-config", config_path, absolute_path=True)
    return _BuiltCommand(argv, (config_path,), environment, pass_fds)


def _get_plugin(env: "LitestarEnv") -> GranianPlugin:
    for plugin in env.app.plugins:
        if isinstance(plugin, GranianPlugin):
            return plugin
    return GranianPlugin()


def _compatibility_process(options: Mapping[str, Any]) -> tuple[str, dict[str, str], tuple[int, ...]]:
    reload_include = tuple(options.get("reload_include") or ())
    reload_exclude = tuple(options.get("reload_exclude") or ())
    fd = options.get("fd")
    environment: dict[str, str] = {}
    if reload_include:
        environment["LITESTAR_GRANIAN_RELOAD_INCLUDES"] = json.dumps(reload_include)
    if reload_exclude:
        environment["LITESTAR_GRANIAN_RELOAD_EXCLUDES"] = json.dumps(reload_exclude)
    if fd is not None:
        environment["LITESTAR_GRANIAN_FILE_DESCRIPTOR"] = str(fd)
    runner_module = "litestar_granian._runner" if environment else "granian"
    return runner_module, environment, (fd,) if fd is not None else ()


def _add_bool(argv: list[str], name: str, value: object) -> None:
    if value is not None:
        argv.append(f"--{name}" if bool(value) else f"--no-{name}")


def _add_value(
    argv: list[str],
    name: str,
    value: object,
    *,
    absolute_path: bool = False,
) -> None:
    if value is None:
        return
    normalized = _value(value)
    if absolute_path:
        normalized = str(Path(normalized).resolve())
    argv.append(f"--{name}={normalized}")


def _add_repeated(
    argv: list[str],
    name: str,
    values: Iterable[object] | None,
    *,
    absolute_path: bool = False,
) -> None:
    if values is None:
        return
    for value in values:
        _add_value(argv, name, value, absolute_path=absolute_path)


def _value(value: object) -> Any:
    return value.value if isinstance(value, Enum) else value
