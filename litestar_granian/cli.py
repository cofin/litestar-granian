import copy
import multiprocessing
import os
import platform
import signal
import subprocess  # noqa: S404
import sys
import tempfile
from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, TypeVar, Union, cast

from granian.cli import Duration, OctalIntType, _pretty_print_default
from granian.cli import EnumType as GranianEnumType
from granian.constants import HTTPModes, Interfaces, Loops, RuntimeModes, SSLProtocols, TaskImpl
from granian.errors import FatalError
from granian.http import HTTP1Settings, HTTP2Settings
from granian.log import LOGGING_CONFIG, LogLevels
from granian.server import Server as Granian
from litestar.cli._utils import (
    LitestarEnv,  # pyright: ignore[reportPrivateImportUsage]
    console,  # pyright: ignore[reportPrivateImportUsage]
    create_ssl_files,  # pyright: ignore[reportPrivateImportUsage]
    isatty,  # type: ignore[attr-defined,unused-ignore]
    show_app_info,  # pyright: ignore[reportPrivateImportUsage]
)
from litestar.cli.commands.core import _server_lifespan  # pyright: ignore[reportPrivateUsage]
from litestar.logging import LoggingConfig
from litestar.serialization import encode_json

try:
    from rich_click import (
        Command,
        Context,
        IntRange,
        Option,
        command,
    )
    from rich_click import Path as ClickPath
    from rich_click import option as click_option
except ImportError:
    from click import (  # type: ignore[no-redef]
        Command,
        Context,
        IntRange,
        Option,
        command,
    )
    from click import Path as ClickPath
    from click import option as click_option  # type: ignore[assignment]


if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.cli._utils import LitestarEnv  # pyright: ignore[reportPrivateImportUsage]


class EnumType(GranianEnumType):
    """A click type for enums."""

    def __init__(self, enum: Any, case_sensitive: bool = False) -> None:
        super().__init__(enum, case_sensitive)


_AnyCallable = Callable[..., Any]
FC = TypeVar("FC", bound=Union[_AnyCallable, Command])


def option(*param_decls: str, cls: "Optional[type[Option]]" = None, **attrs: Any) -> "Callable[[FC], FC]":
    attrs["show_envvar"] = True
    if "default" in attrs:
        attrs["show_default"] = _pretty_print_default(attrs["default"])
    return click_option(*param_decls, cls=cls, **attrs)  # pyright: ignore


@command(name="run", context_settings={"show_default": True}, help="Start application server")
# Server configuration
@option("-H", "--host", help="Host address to bind to", default="127.0.0.1", show_default=True, envvar="LITESTAR_HOST")
@option("-p", "--port", help="Port to bind to", type=int, default=8000, show_default=True, envvar="LITESTAR_PORT")
@option(
    "--uds",
    type=ClickPath(exists=False, writable=True),
    help="Unix Domain Socket path (experimental)",
)
@option(
    "--uds-permissions",
    type=OctalIntType(),
    help="Unix Domain Socket permissions (octal)",
    default=None,
    show_default=False,
)
@option("--http", help="HTTP Version to use (HTTP or HTTP2)", type=HTTPModes, default=HTTPModes.auto.value)
@option("-d", "--debug", help="Run app in debug mode", is_flag=True, envvar="LITESTAR_DEBUG")
@option("-P", "--pdb", "--use-pdb", help="Drop into PDB on an exception", is_flag=True, envvar="LITESTAR_PDB")
# Process & Threading configuration
@option(
    "-W",
    "--wc",
    "--web-concurrency",
    "--workers",
    help="The number of worker processes",
    type=IntRange(min=1, max=multiprocessing.cpu_count() + 1),
    show_default=True,
    default=1,
    envvar=["LITESTAR_WEB_CONCURRENCY", "WEB_CONCURRENCY"],
)
@option(
    "--blocking-threads",
    type=IntRange(1),
    help="Number of blocking threads (per worker)",
)
@option(
    "--blocking-threads-idle-timeout",
    type=Duration(5, 600),
    default=30,
    help=(
        "The maximum amount of time an idle blocking thread will be kept alive "
        "(supports human-readable format like '5m', '30s')"
    ),
)
@option("--runtime-threads", type=IntRange(1), default=1, help="Number of runtime threads (per worker)")
@option(
    "--runtime-blocking-threads",
    type=IntRange(1),
    help="Number of runtime I/O blocking threads (per worker)",
)
@option(
    "--runtime-mode",
    type=EnumType(RuntimeModes),
    default=RuntimeModes.auto,
    help="Runtime mode to use (single/multi threaded/auto-detect)",
)
@option(
    "--loop",
    type=EnumType(Loops),
    default=Loops.auto,
    help="Event loop implementation",
)
@option(
    "--task-impl",
    type=EnumType(TaskImpl),
    default=TaskImpl.asyncio,
    help="Async task implementation to use",
)
@option(
    "--backlog",
    help="Maximum number of connections to hold in backlog (globally)",
    type=IntRange(min=128),
    show_default=True,
    default=1024,
)
@option(
    "--backpressure",
    type=IntRange(1),
    show_default="backlog/workers",
    default=None,
    help="Maximum number of requests to process concurrently (per worker)",
)
# HTTP configuration
@option(
    "--http1-buffer-size",
    type=IntRange(8192),
    default=HTTP1Settings.max_buffer_size,
    help="Sets the maximum buffer size for HTTP/1 connections",
)
@option(
    "--http1-header-read-timeout",
    type=IntRange(1, 60_000),
    default=HTTP1Settings.header_read_timeout,
    help="Sets a timeout (in milliseconds) to read headers",
)
@option(
    "--http1-keep-alive/--no-http1-keep-alive",
    help="Enables or disables HTTP/1 keep-alive",
    default=HTTP1Settings.keep_alive,
    show_default=True,
    is_flag=True,
)
@option(
    "--http1-pipeline-flush/--no-http1-pipeline-flush",
    help="Aggregates HTTP/1 flushes to better support pipelined responses (experimental)",
    default=False,
    is_flag=True,
)
# HTTP/2 specific settings
@option(
    "--http2-adaptive-window/--no-http2-adaptive-window",
    help="Sets whether to use an adaptive flow control for HTTP2",
    default=HTTP2Settings.adaptive_window,
    is_flag=True,
)
@option(
    "--http2-initial-connection-window-size",
    help="Sets the max connection-level flow control for HTTP2",
    type=int,
    show_default=False,
    default=HTTP2Settings.initial_connection_window_size,
)
@option(
    "--http2-initial-stream-window-size",
    help="Sets the `SETTINGS_INITIAL_WINDOW_SIZE` option for HTTP2 stream-level flow control",
    type=int,
    show_default=False,
    default=HTTP2Settings.initial_stream_window_size,
)
@option(
    "--http2-keep-alive-interval",
    help="Sets an interval for HTTP2 Ping frames should be sent to keep a connection alive",
    type=int,
    required=False,
    show_default=False,
    default=None,
)
@option(
    "--http2-keep-alive-timeout",
    help=(
        "Sets a timeout for receiving an acknowledgement of the HTTP2 keep-alive ping "
        "(supports human-readable format like '20s')"
    ),
    type=Duration(1),
    show_default=False,
    default=HTTP2Settings.keep_alive_timeout,
)
@option(
    "--http2-max-concurrent-streams",
    help="Sets the SETTINGS_MAX_CONCURRENT_STREAMS option for HTTP2 connections",
    type=int,
    show_default=False,
    default=HTTP2Settings.max_concurrent_streams,
)
@option(
    "--http2-max-frame-size",
    help="Sets the maximum frame size to use for HTTP2",
    type=int,
    show_default=False,
    default=HTTP2Settings.max_frame_size,
)
@option(
    "--http2-max-headers-size",
    help="Sets the max size of received header frames",
    type=int,
    show_default=False,
    default=HTTP2Settings.max_headers_size,
)
@option(
    "--http2-max-send-buffer-size",
    help="Set the maximum write buffer size for each HTTP/2 stream",
    type=int,
    show_default=False,
    default=HTTP2Settings.max_send_buffer_size,
)
@option("--granian-log/--granian-no-log", "log_enabled", default=True, help="Enable logging")
@option("--granian-log-level", "log_level", type=EnumType(LogLevels), default=LogLevels.info, help="Log level")
@option("--granian-access-log/--granian-no-access-log", "log_access_enabled", default=False, help="Enable access log")
@option("--granian-access-log-fmt", "log_access_fmt", help="Access log format")
# SSL configuration
@option(
    "--ssl-certificate",
    "--ssl-certfile",
    "ssl_certificate",
    type=ClickPath(file_okay=True, exists=False, dir_okay=False, readable=True),
    help="SSL certificate file (Uvicorn-compatible alias: --ssl-certfile)",
    default=None,
    show_default=False,
)
@option(
    "--ssl-keyfile",
    type=ClickPath(file_okay=True, exists=False, dir_okay=False, readable=True),
    help="SSL key file",
    default=None,
    show_default=False,
)
@option(
    "--create-self-signed-cert",
    help="If certificate and key are not found at specified locations, create a self-signed certificate and a key",
    is_flag=True,
    envvar="LITESTAR_CREATE_SELF_SIGNED_CERT",
)
@option("--ssl-keyfile-password", help="SSL key password")
@option(
    "--ssl-protocol-min",
    type=EnumType(SSLProtocols),
    default=SSLProtocols.tls13,
    help="Set the minimum supported protocol for SSL connections.",
)
@option(
    "--ssl-ca",
    type=ClickPath(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),  # type: ignore[type-var]
    help="Root SSL certificate file for client verification",
)
@option(
    "--ssl-crl",
    type=ClickPath(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),  # type: ignore[type-var]
    help="SSL CRL file(s)",
    multiple=True,
)
@option(
    "--ssl-client-verify/--no-ssl-client-verify",
    default=False,
    help="Verify clients SSL certificates",
)
# Logging configuration
@option("--url-path-prefix", help="URL path prefix the app is mounted on", default=None, show_default=False)
# Worker lifecycle
@option(
    "--respawn-failed-workers/--no-respawn-failed-workers",
    help="Enable workers respawn on unexpected exit",
    default=False,
    is_flag=True,
)
@option(
    "--respawn-interval",
    default=3.5,
    help="The number of seconds to sleep between workers respawn",
)
@option(
    "--workers-lifetime",
    type=Duration(60),
    help="The maximum amount of time a worker will be kept alive before respawn (supports human-readable format like '6h', '30m')",
)
@option(
    "--workers-kill-timeout",
    type=Duration(1, 1800),
    help=(
        "The amount of time to wait for killing workers that refused to gracefully stop "
        "(supports human-readable format like '5s', '1m')"
    ),
    default=5,
    show_default="disabled",
)
@option(
    "--workers-max-rss",
    type=IntRange(1),
    help="The maximum amount of memory (in MiB) a worker can consume before respawn",
)
@option(
    "--rss-sample-interval",
    type=Duration(1, 300),
    default=30,
    help="The sample rate in seconds (or a human-readable duration) for the resource monitor",
)
@option(
    "--rss-samples",
    type=IntRange(1),
    default=1,
    help="The number of consecutive samples to consider a worker over resource limit",
)
# Development & Debug options
@option(
    "-r",
    "--reload/--no-reload",
    help="Enable auto reload on application's files changes (requires granian[reload] extra)",
    default=False,
    is_flag=True,
)
@option(
    "--reload-paths",
    "--reload-include",
    "reload_paths",
    type=ClickPath(exists=True, file_okay=True, dir_okay=True, readable=True, path_type=Path),  # type: ignore[type-var]
    help="Paths to watch for changes (Uvicorn-compatible alias: --reload-include)",
    show_default="Working directory",
    multiple=True,
)
@option(
    "--reload-ignore-dirs",
    "--reload-exclude",
    "reload_ignore_dirs",
    help=(
        "Names of directories to ignore changes for. "
        "Extends the default list of directories to ignore in watchfiles' default filter. "
        "Uvicorn-compatible alias: --reload-exclude"
    ),
    multiple=True,
)
@option(
    "--reload-ignore-patterns",
    help=(
        "File/directory name patterns (regex) to ignore changes for. "
        "Extends the default list of patterns to ignore in watchfiles' default filter"
    ),
    multiple=True,
)
@option(
    "--reload-ignore-paths",
    type=ClickPath(exists=False, path_type=Path),  # type: ignore[type-var]
    help="Absolute paths to ignore changes for",
    multiple=True,
)
@option(
    "--reload-tick",
    type=IntRange(50, 5000),
    help="The tick frequency (in milliseconds) the reloader watch for changes",
    default=50,
)
@option(
    "--reload-ignore-worker-failure/--no-reload-ignore-worker-failure",
    default=False,
    help="Ignore worker failures when auto reload is enabled",
)
# Process management
@option(
    "--process-name",
    help="Set a custom name for processes (requires granian[pname] extra)",
)
@option(
    "--pid-file",
    type=ClickPath(exists=False, file_okay=True, dir_okay=False, writable=True, path_type=Path),  # type: ignore[type-var]
    help="A path to write the PID file to",
)
# WebSocket configuration
@option(
    "--ws/--no-ws",
    "ws_enabled",
    default=True,
    help="Enable or disable WebSocket handling",
    show_default=True,
)
# Static file serving (Granian server-level)
@option(
    "--static-path-route",
    help=(
        "URL route prefix for Granian-served static files. Repeat for multi-mount; "
        "paired positionally with --static-path-mount."
    ),
    multiple=True,
)
@option(
    "--static-path-mount",
    type=ClickPath(exists=True, file_okay=False, dir_okay=True, readable=True, path_type=Path),  # type: ignore[type-var]
    help=(
        "Directory path for Granian to serve static files from. Repeat for multi-mount; "
        "paired positionally with --static-path-route."
    ),
    multiple=True,
)
@option(
    "--static-path-dir-to-file",
    type=str,
    default=None,
    help=(
        "Filename to serve for directory requests under a static mount (e.g. 'index.html'). "
        "Enables HTML mode for SPA-style serving."
    ),
)
@option(
    "--static-path-expires",
    type=Duration(0),
    default=86400,
    help=(
        "Cache expiration for Granian static files (supports human-readable format like '1d', '1h'). "
        "Pass 0 to disable caching."
    ),
    show_default=True,
)
@option(
    "--in-subprocess/--no-subprocess",
    "in_subprocess",
    default=True,
    help="Launch Granian in a subprocess.",
    envvar="LITESTAR_GRANIAN_IN_SUBPROCESS",
)
@option(
    "--auto-static/--no-auto-static",
    "auto_static",
    default=False,
    is_flag=True,
    help=(
        "Auto-map Litestar StaticFilesConfig entries to Granian native static serving. "
        "Only legacy StaticFilesConfig is introspected; create_static_files_router() "
        "closures are opaque and must be configured explicitly. Matched routes bypass "
        "ASGI entirely (no guards, middleware, or custom 404 handling)."
    ),
)
@option(
    "--working-dir",
    type=ClickPath(exists=True, file_okay=False, dir_okay=True, readable=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Working directory to use when starting Granian workers.",
)
@option(
    "--env-files",
    type=ClickPath(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),  # type: ignore[type-var]
    multiple=True,
    help="One or more dotenv files to load before starting workers (repeatable).",
)
@option(
    "--log-config",
    type=ClickPath(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),  # type: ignore[type-var]
    default=None,
    help=(
        "Path to a JSON file containing a logging dictConfig. Takes precedence over "
        "--use-litestar-logger when both are set."
    ),
)
@option(
    "--metrics/--no-metrics",
    "metrics_enabled",
    default=False,
    is_flag=True,
    help="Enable Granian's built-in Prometheus metrics endpoint.",
)
@option(
    "--metrics-scrape-interval",
    type=Duration(1, 60),
    default=15,
    help="Metrics sample interval (supports human-readable format like '15s', '1m').",
)
@option(
    "--metrics-address",
    type=str,
    default="127.0.0.1",
    help="Address to bind the metrics endpoint to.",
    show_default=True,
)
@option(
    "--metrics-port",
    type=IntRange(1, 65535),
    default=9090,
    help="Port to bind the metrics endpoint to.",
    show_default=True,
)
@option(
    "--use-litestar-logger/--no-litestar-logger",
    "use_litestar_logger",
    default=False,
    help="Use the default Litestar Queue listener for logging",
    envvar="LITESTAR_GRANIAN_USE_LITESTAR_LOGGER",
)
def run_command(
    app: "Litestar",
    host: str,
    port: int,
    uds: Optional[str],
    uds_permissions: Optional[int],
    http: "HTTPModes",
    wc: int,
    blocking_threads: Optional[int],
    blocking_threads_idle_timeout: int,
    runtime_threads: int,
    runtime_blocking_threads: Optional[int],
    runtime_mode: "RuntimeModes",
    loop: "Loops",
    task_impl: "TaskImpl",
    backlog: int,
    backpressure: Optional[int],
    http1_buffer_size: int,
    http1_header_read_timeout: int,
    http1_keep_alive: bool,
    http1_pipeline_flush: bool,
    http2_adaptive_window: bool,
    http2_initial_connection_window_size: int,
    http2_initial_stream_window_size: int,
    http2_keep_alive_interval: Optional[int],
    http2_keep_alive_timeout: int,
    http2_max_concurrent_streams: int,
    http2_max_frame_size: int,
    http2_max_headers_size: int,
    http2_max_send_buffer_size: int,
    log_enabled: bool,
    log_access_enabled: bool,
    log_access_fmt: Optional[str],
    log_level: "LogLevels",
    ssl_certificate: Optional[Path],
    ssl_keyfile: Optional[Path],
    ssl_keyfile_password: Optional[str],
    ssl_protocol_min: "SSLProtocols",
    ssl_ca: Optional[Path],
    ssl_crl: Optional[list[Path]],
    ssl_client_verify: bool,
    create_self_signed_cert: bool,
    url_path_prefix: Optional[str],
    respawn_failed_workers: bool,
    respawn_interval: float,
    workers_lifetime: Optional[int],
    workers_kill_timeout: Optional[int],
    workers_max_rss: Optional[int],
    rss_sample_interval: int,
    rss_samples: int,
    reload: bool,
    reload_paths: Optional[list[Path]],
    reload_ignore_dirs: Optional[list[str]],
    reload_ignore_patterns: Optional[list[str]],
    reload_ignore_paths: Optional[list[Path]],
    reload_tick: int,
    reload_ignore_worker_failure: bool,
    process_name: Optional[str],
    pid_file: Optional[Path],
    static_path_route: "tuple[str, ...]",
    static_path_mount: "tuple[Path, ...]",
    static_path_dir_to_file: Optional[str],
    static_path_expires: int,
    ws_enabled: bool,
    debug: bool,
    pdb: bool,
    in_subprocess: bool,
    auto_static: bool,
    working_dir: Optional[Path],
    env_files: "tuple[Path, ...]",
    log_config: Optional[Path],
    metrics_enabled: bool,
    metrics_scrape_interval: int,
    metrics_address: str,
    metrics_port: int,
    use_litestar_logger: bool,
    ctx: Context,
) -> None:  # sourcery skip: low-code-quality
    """Run a Litestar app.

    The app can be either passed as a module path in the form of <module name>.<submodule>:<app instance or factory>,
    set as an environment variable LITESTAR_APP with the same format or automatically discovered from one of these
    canonical paths: app.py, asgi.py, application.py or app/__init__.py. When auto-discovering application factories,
    functions with the name ``create_app`` are considered, or functions that are annotated as returning a ``Litestar``
    instance.
    """

    if debug:
        app.debug = True
        os.environ["LITESTAR_DEBUG"] = "1"
    if pdb:
        os.environ["LITESTAR_PDB"] = "1"
    os.environ["LITESTAR_PORT"] = str(port)
    quiet_console = os.getenv("LITESTAR_QUIET_CONSOLE") or False
    if callable(ctx.obj):
        ctx.obj = ctx.obj()
    else:
        if debug:
            ctx.obj.app.debug = True
        if pdb:
            ctx.obj.app.pdb_on_exception = True

    env: LitestarEnv = ctx.obj
    del ctx
    workers = wc

    if auto_static and not static_path_mount:
        detected_routes, detected_mounts, detected_dir_to_file = _detect_static_from_litestar(env.app)
        if detected_routes:
            static_path_route = tuple(detected_routes)
            static_path_mount = tuple(detected_mounts)
            if static_path_dir_to_file is None and detected_dir_to_file is not None:
                static_path_dir_to_file = detected_dir_to_file
            console.print(
                f"[cyan]auto-static:[/] mapped {len(detected_routes)} Litestar StaticFilesConfig "
                f"entries to Granian native serving."
            )

    if not metrics_enabled and _has_prometheus_plugin(env.app):
        metrics_enabled = True
        console.print(
            "[cyan]auto-metrics:[/] PrometheusPlugin detected; enabling Granian metrics endpoint "
            f"on {metrics_address}:{metrics_port}."
        )

    if create_self_signed_cert:
        cert, key = create_ssl_files(str(ssl_certificate), str(ssl_keyfile), host)
        ssl_certificate = ssl_certificate or Path(cert) if cert is not None else None  # pyright: ignore[reportUnnecessaryComparison]
        ssl_keyfile = ssl_keyfile or Path(key) if key is not None else None  # pyright: ignore[reportUnnecessaryComparison]

    if not quiet_console and isatty():
        msg = "Starting [blue]Granian[/] server process"
        console.rule(msg, align="left")
        show_app_info(env.app)
    with _server_lifespan(env.app):
        if in_subprocess:
            _run_granian_in_subprocess(
                env=env,
                port=port,
                wc=workers,
                host=host,
                http=http,
                blocking_threads=blocking_threads,
                blocking_threads_idle_timeout=blocking_threads_idle_timeout,
                runtime_threads=runtime_threads,
                runtime_blocking_threads=runtime_blocking_threads,
                runtime_mode=runtime_mode,
                loop=loop,
                task_impl=task_impl,
                backlog=backlog,
                backpressure=backpressure,
                http1_buffer_size=http1_buffer_size,
                http1_header_read_timeout=http1_header_read_timeout,
                http1_keep_alive=http1_keep_alive,
                http1_pipeline_flush=http1_pipeline_flush,
                http2_adaptive_window=http2_adaptive_window,
                http2_initial_connection_window_size=http2_initial_connection_window_size,
                http2_initial_stream_window_size=http2_initial_stream_window_size,
                http2_keep_alive_interval=http2_keep_alive_interval,
                http2_keep_alive_timeout=http2_keep_alive_timeout,
                http2_max_concurrent_streams=http2_max_concurrent_streams,
                http2_max_frame_size=http2_max_frame_size,
                http2_max_headers_size=http2_max_headers_size,
                http2_max_send_buffer_size=http2_max_send_buffer_size,
                log_enabled=log_enabled,
                log_access_enabled=log_access_enabled,
                log_access_fmt=log_access_fmt,
                log_level=log_level,
                ssl_certificate=ssl_certificate,
                ssl_keyfile=ssl_keyfile,
                ssl_keyfile_password=ssl_keyfile_password,
                ssl_protocol_min=ssl_protocol_min,
                ssl_ca=ssl_ca,
                ssl_crl=ssl_crl,
                ssl_client_verify=ssl_client_verify,
                url_path_prefix=url_path_prefix,
                respawn_failed_workers=respawn_failed_workers,
                respawn_interval=respawn_interval,
                workers_lifetime=workers_lifetime,
                workers_kill_timeout=workers_kill_timeout,
                workers_max_rss=workers_max_rss,
                rss_sample_interval=rss_sample_interval,
                rss_samples=rss_samples,
                uds=uds,
                uds_permissions=uds_permissions,
                reload=reload,
                reload_paths=reload_paths,
                reload_ignore_paths=reload_ignore_paths,
                reload_ignore_dirs=reload_ignore_dirs,
                reload_ignore_patterns=reload_ignore_patterns,
                reload_tick=reload_tick,
                reload_ignore_worker_failure=reload_ignore_worker_failure,
                process_name=process_name,
                pid_file=pid_file,
                static_path_route=static_path_route,
                static_path_mount=static_path_mount,
                static_path_dir_to_file=static_path_dir_to_file,
                static_path_expires=static_path_expires,
                ws_enabled=ws_enabled,
                working_dir=working_dir,
                env_files=env_files,
                log_config=log_config,
                metrics_enabled=metrics_enabled,
                metrics_scrape_interval=metrics_scrape_interval,
                metrics_address=metrics_address,
                metrics_port=metrics_port,
                use_litestar_logger=use_litestar_logger,
            )
        else:
            _run_granian(
                env=env,
                port=port,
                wc=workers,
                host=host,
                http=http,
                blocking_threads=blocking_threads,
                blocking_threads_idle_timeout=blocking_threads_idle_timeout,
                runtime_threads=runtime_threads,
                runtime_blocking_threads=runtime_blocking_threads,
                runtime_mode=runtime_mode,
                loop=loop,
                task_impl=task_impl,
                backlog=backlog,
                backpressure=backpressure,
                http1_buffer_size=http1_buffer_size,
                http1_header_read_timeout=http1_header_read_timeout,
                http1_keep_alive=http1_keep_alive,
                http1_pipeline_flush=http1_pipeline_flush,
                http2_adaptive_window=http2_adaptive_window,
                http2_initial_connection_window_size=http2_initial_connection_window_size,
                http2_initial_stream_window_size=http2_initial_stream_window_size,
                http2_keep_alive_interval=http2_keep_alive_interval,
                http2_keep_alive_timeout=http2_keep_alive_timeout,
                http2_max_concurrent_streams=http2_max_concurrent_streams,
                http2_max_frame_size=http2_max_frame_size,
                http2_max_headers_size=http2_max_headers_size,
                http2_max_send_buffer_size=http2_max_send_buffer_size,
                log_enabled=log_enabled,
                log_access_enabled=log_access_enabled,
                log_access_fmt=log_access_fmt,
                log_level=log_level,
                ssl_certificate=ssl_certificate,
                ssl_keyfile=ssl_keyfile,
                ssl_keyfile_password=ssl_keyfile_password,
                ssl_protocol_min=ssl_protocol_min,
                ssl_ca=ssl_ca,
                ssl_crl=ssl_crl,
                ssl_client_verify=ssl_client_verify,
                url_path_prefix=url_path_prefix,
                respawn_failed_workers=respawn_failed_workers,
                respawn_interval=respawn_interval,
                workers_lifetime=workers_lifetime,
                workers_kill_timeout=workers_kill_timeout,
                workers_max_rss=workers_max_rss,
                rss_sample_interval=rss_sample_interval,
                rss_samples=rss_samples,
                uds=uds,
                uds_permissions=uds_permissions,
                reload=reload,
                reload_paths=reload_paths,
                reload_ignore_paths=reload_ignore_paths,
                reload_ignore_dirs=reload_ignore_dirs,
                reload_ignore_patterns=reload_ignore_patterns,
                reload_tick=reload_tick,
                reload_ignore_worker_failure=reload_ignore_worker_failure,
                process_name=process_name,
                pid_file=pid_file,
                static_path_route=static_path_route,
                static_path_mount=static_path_mount,
                static_path_dir_to_file=static_path_dir_to_file,
                static_path_expires=static_path_expires,
                ws_enabled=ws_enabled,
                working_dir=working_dir,
                env_files=env_files,
                log_config=log_config,
                metrics_enabled=metrics_enabled,
                metrics_scrape_interval=metrics_scrape_interval,
                metrics_address=metrics_address,
                metrics_port=metrics_port,
                use_litestar_logger=use_litestar_logger,
            )


def _run_granian(
    env: "LitestarEnv",
    host: str,
    port: int,
    uds: Optional[str],
    uds_permissions: Optional[int],
    http: "HTTPModes",
    wc: int,
    blocking_threads: Optional[int],
    blocking_threads_idle_timeout: int,
    runtime_threads: int,
    runtime_blocking_threads: Optional[int],
    runtime_mode: "RuntimeModes",
    loop: "Loops",
    task_impl: "TaskImpl",
    backlog: int,
    backpressure: Optional[int],
    http1_buffer_size: int,
    http1_header_read_timeout: int,
    http1_keep_alive: bool,
    http1_pipeline_flush: bool,
    http2_adaptive_window: bool,
    http2_initial_connection_window_size: int,
    http2_initial_stream_window_size: int,
    http2_keep_alive_interval: Optional[int],
    http2_keep_alive_timeout: int,
    http2_max_concurrent_streams: int,
    http2_max_frame_size: int,
    http2_max_headers_size: int,
    http2_max_send_buffer_size: int,
    log_enabled: bool,
    log_access_enabled: bool,
    log_access_fmt: Optional[str],
    log_level: "LogLevels",
    ssl_certificate: Optional[Path],
    ssl_keyfile: Optional[Path],
    ssl_keyfile_password: Optional[str],
    ssl_protocol_min: "SSLProtocols",
    ssl_ca: Optional[Path],
    ssl_crl: Optional[list[Path]],
    ssl_client_verify: bool,
    url_path_prefix: Optional[str],
    respawn_failed_workers: bool,
    respawn_interval: float,
    workers_lifetime: Optional[int],
    workers_kill_timeout: Optional[int],
    workers_max_rss: Optional[int],
    rss_sample_interval: int,
    rss_samples: int,
    reload: bool,
    reload_paths: Optional[list[Path]],
    reload_ignore_dirs: Optional[list[str]],
    reload_ignore_patterns: Optional[list[str]],
    reload_ignore_paths: Optional[list[Path]],
    reload_tick: int,
    reload_ignore_worker_failure: bool,
    process_name: Optional[str],
    pid_file: Optional[Path],
    static_path_route: "tuple[str, ...]",
    static_path_mount: "tuple[Path, ...]",
    static_path_dir_to_file: Optional[str],
    static_path_expires: int,
    ws_enabled: bool,
    working_dir: Optional[Path],
    env_files: "tuple[Path, ...]",
    log_config: Optional[Path],
    metrics_enabled: bool,
    metrics_scrape_interval: int,
    metrics_address: str,
    metrics_port: int,
    use_litestar_logger: bool,
) -> None:
    if reload:
        multiprocessing.set_start_method("spawn", force=True)

    if log_config is not None:
        import json as _json

        log_dictconfig = _json.loads(Path(log_config).read_text(encoding="utf-8"))
    else:
        log_dictconfig = _get_logging_config(env, use_litestar_logger)
    if http.value == HTTPModes.http2.value:
        http1_settings = None
        http2_settings = HTTP2Settings(
            adaptive_window=http2_adaptive_window,
            initial_connection_window_size=http2_initial_connection_window_size,
            initial_stream_window_size=http2_initial_stream_window_size,
            keep_alive_interval=http2_keep_alive_interval,
            keep_alive_timeout=http2_keep_alive_timeout,
            max_concurrent_streams=http2_max_concurrent_streams,
            max_frame_size=http2_max_frame_size,
            max_headers_size=http2_max_headers_size,
            max_send_buffer_size=http2_max_send_buffer_size,
        )

    else:
        http1_settings = HTTP1Settings(
            header_read_timeout=http1_header_read_timeout,
            keep_alive=http1_keep_alive,
            max_buffer_size=http1_buffer_size,
            pipeline_flush=http1_pipeline_flush,
        )
        http2_settings = None
    app_path = env.app_path
    is_factory = env.is_app_factory
    # Build server arguments
    server_args: dict[str, Any] = {
        "address": host,
        "port": port,
        "interface": Interfaces.ASGI,
        "workers": wc,
        "blocking_threads": blocking_threads,
        "blocking_threads_idle_timeout": blocking_threads_idle_timeout,
        "runtime_threads": runtime_threads,
        "runtime_blocking_threads": runtime_blocking_threads,
        "runtime_mode": runtime_mode,
        "loop": loop,
        "task_impl": task_impl,
        "http": http,
        "websockets": ws_enabled and http.value != HTTPModes.http2.value,
        "backlog": backlog,
        "backpressure": backpressure,
        "http1_settings": http1_settings,
        "http2_settings": http2_settings,
        "log_enabled": log_enabled,
        "log_access": log_access_enabled,
        "log_access_format": log_access_fmt,
        "log_level": log_level,
        "log_dictconfig": log_dictconfig,
        "ssl_cert": ssl_certificate,
        "ssl_key": ssl_keyfile,
        "ssl_key_password": ssl_keyfile_password,
        "ssl_protocol_min": ssl_protocol_min,
        "ssl_ca": ssl_ca,
        "ssl_crl": ssl_crl,
        "ssl_client_verify": ssl_client_verify,
        "url_path_prefix": url_path_prefix,
        "respawn_failed_workers": respawn_failed_workers,
        "respawn_interval": respawn_interval,
        "workers_lifetime": workers_lifetime,
        "workers_kill_timeout": workers_kill_timeout,
        "workers_max_rss": workers_max_rss,
        "rss_sample_interval": rss_sample_interval,
        "rss_samples": rss_samples,
        "uds": Path(uds) if uds else None,
        "uds_permissions": uds_permissions,
        "factory": is_factory,
        "reload": reload,
        "reload_paths": reload_paths,
        "reload_ignore_paths": reload_ignore_paths,
        "reload_ignore_dirs": reload_ignore_dirs,
        "reload_ignore_patterns": reload_ignore_patterns,
        "reload_tick": reload_tick,
        "reload_ignore_worker_failure": reload_ignore_worker_failure,
        "process_name": process_name,
        "pid_file": pid_file,
    }

    if static_path_mount:
        server_args["static_path_route"] = list(static_path_route)
        server_args["static_path_mount"] = [Path(p) for p in static_path_mount]
        server_args["static_path_expires"] = static_path_expires
        if static_path_dir_to_file is not None:
            server_args["static_path_dir_to_file"] = static_path_dir_to_file

    if working_dir is not None:
        server_args["working_dir"] = working_dir
    if env_files:
        server_args["env_files"] = [Path(p) for p in env_files]

    server_args["metrics_enabled"] = metrics_enabled
    if metrics_enabled:
        server_args["metrics_scrape_interval"] = metrics_scrape_interval
        server_args["metrics_address"] = metrics_address
        server_args["metrics_port"] = metrics_port

    server = Granian(app_path, **server_args)

    try:
        server.serve()
    except FatalError as e:
        console.print(f"[red]Fatal Granian error: {e}[/]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("[yellow]Granian workers stopped[/]")
    else:
        console.print("[yellow]Granian workers stopped[/]")


_DEFAULT_FORMATTER_FMT = "%(levelname)s - %(asctime)s - %(name)s - %(module)s - %(message)s"
_QUEUE_HANDLER_CLASSES = (
    "litestar.logging.standard.QueueListenerHandler",
    "logging.handlers.QueueHandler",
    "logging.handlers.QueueListener",
)


def _detect_static_from_litestar(
    app: "Litestar",
) -> "tuple[list[str], list[Path], Optional[str]]":
    """Return route/mount/dir_to_file tuples derived from Litestar StaticFilesConfig.

    Only legacy single-directory, local-filesystem configs are eligible.
    Entries with guards, send_as_attachment, or multi-directory fallthrough
    are skipped with a console warning.
    """
    from litestar.file_system import BaseLocalFileSystem

    configs = getattr(app, "static_files_config", None)
    if not configs:
        return [], [], None
    routes: list[str] = []
    mounts: list[Path] = []
    dir_to_file: Optional[str] = None
    for cfg in configs:
        directories = list(getattr(cfg, "directories", []) or [])
        if len(directories) != 1:
            console.print(
                f"[yellow]auto-static: skipping {cfg.path!r} — "
                f"expected exactly 1 directory, got {len(directories)}[/]"
            )
            continue
        fs = getattr(cfg, "file_system", None)
        if fs is not None and not isinstance(fs, BaseLocalFileSystem):
            console.print(
                f"[yellow]auto-static: skipping {cfg.path!r} — custom file_system is not supported[/]"
            )
            continue
        if getattr(cfg, "guards", None):
            console.print(
                f"[yellow]auto-static: skipping {cfg.path!r} — guards are not supported by Granian native serving[/]"
            )
            continue
        if getattr(cfg, "send_as_attachment", False):
            console.print(
                f"[yellow]auto-static: skipping {cfg.path!r} — send_as_attachment is not supported[/]"
            )
            continue
        routes.append(cfg.path)
        mounts.append(Path(directories[0]))
        if getattr(cfg, "html_mode", False) and dir_to_file is None:
            dir_to_file = "index.html"
    return routes, mounts, dir_to_file


def _has_prometheus_plugin(app: "Litestar") -> bool:
    """Return True if Litestar's PrometheusPlugin is installed on the app."""
    try:
        from litestar.plugins.prometheus import PrometheusPlugin
    except ImportError:
        return False
    plugins = getattr(app, "plugins", []) or []
    return any(isinstance(p, PrometheusPlugin) for p in plugins)


def _is_queue_handler(handler: dict[str, Any]) -> bool:
    handler_class = handler.get("class") or handler.get("()")
    if isinstance(handler_class, str) and any(cls in handler_class for cls in _QUEUE_HANDLER_CLASSES):
        return True
    return "listener" in handler


def _neutralize_queue_handlers_for_platform(log_dictconfig: dict[str, Any]) -> None:
    """Rewrite queue-based handlers to ``StreamHandler`` on spawn platforms.

    On Linux (fork workers), each worker calls ``dictConfig`` fresh so queue
    listeners are safe. On macOS / Windows (spawn), multiple worker processes
    would each spin a listener thread racing on stdout — the root cause of
    #21 / #41's "logs after close" and interleaved output. ``StreamHandler``
    has no background thread and flushes on write.
    """
    if sys.platform == "linux":
        return
    handlers = log_dictconfig.get("handlers")
    if not isinstance(handlers, dict):
        return
    for name, handler in list(handlers.items()):
        if not isinstance(handler, dict) or not _is_queue_handler(handler):
            continue
        replacement: dict[str, Any] = {"class": "logging.StreamHandler"}
        if "formatter" in handler:
            replacement["formatter"] = handler["formatter"]
        if "level" in handler:
            replacement["level"] = handler["level"]
        handlers[name] = replacement


def _get_logging_config(env: "LitestarEnv", use_litestar_logger: bool) -> dict[str, Any]:
    """Build a safe logging dictconfig for the Granian server.

    Always returns a fresh copy — never the shared ``granian.log.LOGGING_CONFIG``
    module dict. On spawn platforms, queue-based handlers are neutralized to
    ``StreamHandler`` to avoid worker-process listener races.

    Args:
        env: The Litestar environment.
        use_litestar_logger: Whether to derive the config from the user's
            ``LoggingConfig`` instead of Granian's defaults.

    Returns:
        A dictConfig-ready mapping with ``version: 1`` set.
    """
    log_dictconfig = copy.deepcopy(LOGGING_CONFIG)

    if not use_litestar_logger:
        _neutralize_queue_handlers_for_platform(log_dictconfig)
        log_dictconfig["version"] = 1
        return log_dictconfig

    log_dictconfig.setdefault("formatters", {})
    if log_dictconfig["formatters"].get("generic") is None:
        log_dictconfig["formatters"]["generic"] = {
            "()": "logging.Formatter",
            "fmt": _DEFAULT_FORMATTER_FMT,
        }
    if log_dictconfig["formatters"].get("access") is None:
        log_dictconfig["formatters"]["access"] = {
            "()": "logging.Formatter",
            "fmt": _DEFAULT_FORMATTER_FMT,
        }

    existing_logging_config = cast(
        "Optional[LoggingConfig]",
        env.app.logging_config.standard_lib_logging_config  # pyright: ignore[reportAttributeAccessIssue]
        if env.app.logging_config is not None and hasattr(env.app.logging_config, "standard_lib_logging_config")
        else env.app.logging_config
        if env.app.logging_config is not None and isinstance(env.app.logging_config, LoggingConfig)
        else None,
    )

    if existing_logging_config is not None:
        # Build the Granian dictconfig from the user's LoggingConfig snapshot.
        # Do not call ``existing_logging_config.configure()`` here — the
        # ``GranianPlugin.on_app_init`` hook already configured parent-process
        # logging, and re-applying it from an unrelated codepath causes
        # double-configuration surprises (and breaks on platforms where the
        # handler class cannot be instantiated a second time).
        # Whitelist only the keys ``logging.config.dictConfig`` understands;
        # Litestar-specific fields like ``exception_logging_handler`` hold
        # callables that would break serialization downstream.
        dictconfig_keys = {
            "formatters",
            "filters",
            "handlers",
            "loggers",
            "root",
            "disable_existing_loggers",
        }
        log_dictconfig = {
            field.name: copy.deepcopy(getattr(existing_logging_config, field.name))
            for field in fields(existing_logging_config)
            if field.name in dictconfig_keys
            and getattr(existing_logging_config, field.name) is not None
        }

        loggers = log_dictconfig.setdefault("loggers", {})
        if loggers.get("_granian") is None:
            loggers["_granian"] = {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            }
        if loggers.get("granian.access") is None:
            loggers["granian.access"] = {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            }
        formatters = log_dictconfig.setdefault("formatters", {})
        if formatters.get("generic") is None:
            formatters["generic"] = formatters.get("standard", {"format": _DEFAULT_FORMATTER_FMT})

    _neutralize_queue_handlers_for_platform(log_dictconfig)
    log_dictconfig["version"] = 1
    return log_dictconfig


def _convert_granian_args(args: dict[str, Any]) -> list[str]:
    process_args = []
    for arg, value in args.items():
        if isinstance(value, bool):
            if value:
                process_args.append(f"--{arg}")
            else:
                process_args.append(f"--no-{arg}")
        elif isinstance(value, (tuple, list)):
            process_args.extend(f"--{arg}={item}" for item in value)
        else:
            process_args.append(f"--{arg}={value}")

    return process_args


def _run_granian_in_subprocess(
    *,
    env: "LitestarEnv",
    host: str,
    port: int,
    uds: Optional[str],
    uds_permissions: Optional[int],
    http: "HTTPModes",
    wc: int,
    blocking_threads: Optional[int],
    blocking_threads_idle_timeout: int,
    runtime_threads: int,
    runtime_blocking_threads: Optional[int],
    runtime_mode: "RuntimeModes",
    loop: "Loops",
    task_impl: "TaskImpl",
    backlog: int,
    backpressure: Optional[int],
    http1_buffer_size: int,
    http1_header_read_timeout: int,
    http1_keep_alive: bool,
    http1_pipeline_flush: bool,
    http2_adaptive_window: bool,
    http2_initial_connection_window_size: int,
    http2_initial_stream_window_size: int,
    http2_keep_alive_interval: Optional[int],
    http2_keep_alive_timeout: int,
    http2_max_concurrent_streams: int,
    http2_max_frame_size: int,
    http2_max_headers_size: int,
    http2_max_send_buffer_size: int,
    log_enabled: bool,
    log_access_enabled: bool,
    log_access_fmt: Optional[str],
    log_level: "LogLevels",
    ssl_certificate: Optional[Path],
    ssl_keyfile: Optional[Path],
    ssl_keyfile_password: Optional[str],
    ssl_protocol_min: "SSLProtocols",
    ssl_ca: Optional[Path],
    ssl_crl: Optional[list[Path]],
    ssl_client_verify: bool,
    url_path_prefix: Optional[str],
    respawn_failed_workers: bool,
    respawn_interval: float,
    workers_lifetime: Optional[int],
    workers_kill_timeout: Optional[int],
    workers_max_rss: Optional[int],
    rss_sample_interval: int,
    rss_samples: int,
    reload: bool,
    reload_paths: Optional[list[Path]],
    reload_ignore_dirs: Optional[list[str]],
    reload_ignore_patterns: Optional[list[str]],
    reload_ignore_paths: Optional[list[Path]],
    reload_tick: int,
    reload_ignore_worker_failure: bool,
    process_name: Optional[str],
    pid_file: Optional[Path],
    static_path_route: "tuple[str, ...]",
    static_path_mount: "tuple[Path, ...]",
    static_path_dir_to_file: Optional[str],
    static_path_expires: int,
    ws_enabled: bool,
    working_dir: Optional[Path] = None,
    env_files: "tuple[Path, ...]" = (),
    log_config: Optional[Path] = None,
    metrics_enabled: bool = False,
    metrics_scrape_interval: int = 15,
    metrics_address: str = "127.0.0.1",
    metrics_port: int = 9090,
    use_litestar_logger: bool = False,
) -> None:
    process_args: dict[str, Any] = {
        "reload": reload,
        "host": host,
        "port": port,
        "interface": Interfaces.ASGI.value,
        "http": http.value,
        "workers": wc,
        "runtime-mode": runtime_mode.value,
        "loop": loop.value,
        "task-impl": task_impl.value,
        "backlog": backlog,
        "log-level": log_level.value,
        "ssl-protocol-min": ssl_protocol_min.value,
        "ssl-client-verify": ssl_client_verify,
        "rss-sample-interval": rss_sample_interval,
        "rss-samples": rss_samples,
        "reload-tick": reload_tick,
        "reload-ignore-worker-failure": reload_ignore_worker_failure,
    }
    if env.is_app_factory:
        process_args["factory"] = env.is_app_factory
    if respawn_failed_workers:
        process_args["respawn-failed-workers"] = True
    if respawn_interval:
        process_args["respawn-interval"] = respawn_interval
    if reload_paths:
        process_args["reload-paths"] = [str(Path(d).absolute()) for d in reload_paths]
    if reload_ignore_dirs:
        process_args["reload-ignore-dirs"] = reload_ignore_dirs
    if reload_ignore_patterns:
        process_args["reload-ignore-patterns"] = reload_ignore_patterns
    if reload_ignore_paths:
        process_args["reload-ignore-paths"] = [str(Path(d).absolute()) for d in reload_ignore_paths]
    if backpressure:
        process_args["backpressure"] = backpressure
    if workers_lifetime:
        process_args["workers-lifetime"] = workers_lifetime
    if log_access_enabled:
        process_args["access-log"] = log_access_enabled
    if log_access_fmt:
        process_args["access-log-fmt"] = log_access_fmt
    if workers_kill_timeout:
        process_args["workers-kill-timeout"] = workers_kill_timeout
    if workers_max_rss:
        process_args["workers-max-rss"] = workers_max_rss
    if uds:
        process_args["uds"] = str(Path(uds).absolute())
    if uds_permissions:
        process_args["uds-permissions"] = uds_permissions
    if blocking_threads:
        process_args["blocking-threads"] = blocking_threads
    process_args["blocking-threads-idle-timeout"] = blocking_threads_idle_timeout
    process_args["runtime-threads"] = runtime_threads
    if runtime_blocking_threads:
        process_args["runtime-blocking-threads"] = runtime_blocking_threads
    if runtime_mode:
        process_args["runtime-mode"] = runtime_mode.value
    if not log_enabled:
        process_args["no-log"] = True
    if http.value in {HTTPModes.http1.value, HTTPModes.auto.value}:
        process_args["http1-buffer-size"] = http1_buffer_size
        process_args["http1-header-read-timeout"] = http1_header_read_timeout
        process_args["http1-keep-alive"] = http1_keep_alive
        process_args["http1-pipeline-flush"] = http1_pipeline_flush
        process_args["ws"] = ws_enabled
    if http.value == HTTPModes.http2.value:
        process_args["http2-adaptive-window"] = http2_adaptive_window
        process_args["http2-initial-connection-window-size"] = http2_initial_connection_window_size
        process_args["http2-initial-stream-window-size"] = http2_initial_stream_window_size
        if http2_keep_alive_interval is not None:
            process_args["http2-keep-alive-interval"] = http2_keep_alive_interval
        process_args["http2-keep-alive-timeout"] = http2_keep_alive_timeout
        process_args["http2-max-concurrent-streams"] = http2_max_concurrent_streams
        process_args["http2-max-frame-size"] = http2_max_frame_size
        process_args["http2-max-headers-size"] = http2_max_headers_size
        process_args["http2-max-send-buffer-size"] = http2_max_send_buffer_size
        # websockets are not supported in http2 mode
        process_args["ws"] = False
    if url_path_prefix is not None:
        process_args["url-path-prefix"] = url_path_prefix
    if ssl_certificate is not None:
        process_args["ssl-certificate"] = ssl_certificate
    if ssl_keyfile is not None:
        process_args["ssl-keyfile"] = ssl_keyfile
    if ssl_keyfile_password is not None:
        process_args["ssl-keyfile-password"] = ssl_keyfile_password
    if ssl_ca is not None:
        process_args["ssl-ca"] = ssl_ca
    if ssl_crl is not None:
        process_args["ssl-crl"] = ssl_crl
    if process_name is not None:
        process_args["process-name"] = process_name
    if pid_file is not None:
        process_args["pid-file"] = str(Path(pid_file).absolute())
    if static_path_mount:
        process_args["static-path-route"] = list(static_path_route)
        process_args["static-path-mount"] = [str(Path(p).absolute()) for p in static_path_mount]
        process_args["static-path-expires"] = static_path_expires
        if static_path_dir_to_file is not None:
            process_args["static-path-dir-to-file"] = static_path_dir_to_file
    if working_dir is not None:
        process_args["working-dir"] = str(Path(working_dir).absolute())
    if env_files:
        process_args["env-files"] = [str(Path(p).absolute()) for p in env_files]
    if metrics_enabled:
        process_args["metrics"] = True
        process_args["metrics-scrape-interval"] = metrics_scrape_interval
        process_args["metrics-address"] = metrics_address
        process_args["metrics-port"] = metrics_port

    log_config_tempfile: Optional[Path] = None
    if log_config is not None:
        process_args["log-config"] = str(Path(log_config).absolute())
    elif use_litestar_logger:
        log_dictconfig = _get_logging_config(env, use_litestar_logger=True)
        fd, log_config_path = tempfile.mkstemp(prefix="litestar-granian-logconf-", suffix=".json")
        try:
            with os.fdopen(fd, "wb") as fp:
                fp.write(encode_json(log_dictconfig))
        except Exception:
            Path(log_config_path).unlink(missing_ok=True)
            raise
        log_config_tempfile = Path(log_config_path)
        process_args["log-config"] = str(log_config_tempfile)

    command = [sys.executable, "-m", "granian", env.app_path, *_convert_granian_args(process_args)]

    process = subprocess.Popen(command, restore_signals=False)

    # In subprocess mode, we want to let the child process handle SIGINT (Ctrl+C).
    # Since the child is in the same process group, it will receive the signal
    # directly from the terminal. If we don't ignore it here, the parent will
    # catch KeyboardInterrupt and try to send SIGTERM to the child, causing a
    # race condition and potential instability (double signal).
    #
    # We save the original handler to restore it later.
    original_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)

    try:
        process.wait()
    except KeyboardInterrupt:
        # This block might be reached if we receive a different signal that raises
        # KeyboardInterrupt (unlikely with SIG_IGN for SIGINT), or if the
        # wait is interrupted by another signal handler.
        if platform.system() == "Windows":
            process.send_signal(signal.CTRL_C_EVENT)  # type: ignore[attr-defined]
        else:
            process.send_signal(signal.SIGTERM)
    finally:
        # Restore the original signal handler
        signal.signal(signal.SIGINT, original_handler)

        # Always ensure the process is reaped
        try:
            if process.poll() is None:
                process.terminate()
                process.wait()
        except KeyboardInterrupt:
            if platform.system() != "Windows":
                process.send_signal(signal.SIGKILL)
            process.kill()
        if log_config_tempfile is not None:
            log_config_tempfile.unlink(missing_ok=True)
        console.print("[yellow]Granian workers stopped.[/]")
