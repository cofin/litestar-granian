"""Define the Granian-backed ``litestar run`` compatibility command."""

import os
import sys
import sysconfig
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from click import UsageError
from click.exceptions import Exit
from granian.cli import Duration, OctalIntType, _pretty_print_default
from granian.cli import EnumType as GranianEnumType
from granian.constants import HTTPModes, Loops, RuntimeModes, SSLProtocols, TaskImpl
from granian.http import HTTP1Settings, HTTP2Settings
from granian.log import LogLevels
from litestar.cli._utils import (
    LitestarEnv,  # pyright: ignore[reportPrivateImportUsage]
    console,  # pyright: ignore[reportPrivateImportUsage]
    create_ssl_files,  # pyright: ignore[reportPrivateImportUsage]
    isatty,  # type: ignore[attr-defined,unused-ignore]
    show_app_info,  # pyright: ignore[reportPrivateImportUsage]
)
from litestar.cli.commands.core import (
    CommaSplittedPath,
    _server_lifespan,  # pyright: ignore[reportPrivateUsage]
)

from litestar_granian.command import _build_granian_command
from litestar_granian.supervisor import _GranianSupervisor, _SignalForwarder

try:
    from rich_click import Command, Context, IntRange, Option, command
    from rich_click import Path as ClickPath
    from rich_click import option as click_option
except ImportError:
    from click import Command, Context, IntRange, Option, command  # type: ignore[no-redef]
    from click import Path as ClickPath
    from click import option as click_option  # type: ignore[assignment]

if TYPE_CHECKING:
    from litestar import Litestar


class _EnumChoice(GranianEnumType):
    """A Click type that returns members of the supplied enum."""

    def __init__(self, enum: Any, case_sensitive: bool = False) -> None:
        super().__init__(enum, case_sensitive)


_AnyCallable = Callable[..., Any]
FC = TypeVar("FC", bound=_AnyCallable | Command)

_GRANIAN_ENV_OVERRIDES = {
    "--workers": "GRANIAN_WORKERS",
    "--ws": "GRANIAN_WEBSOCKETS",
    "--granian-log": "GRANIAN_LOG_ENABLED",
    "--granian-log-level": "GRANIAN_LOG_LEVEL",
    "--granian-access-log": "GRANIAN_LOG_ACCESS_ENABLED",
    "--granian-access-log-fmt": "GRANIAN_LOG_ACCESS_FMT",
    "--ssl-certfile": "GRANIAN_SSL_CERTIFICATE",
    "--unix-domain-socket": "GRANIAN_UDS",
    "--reload-dir": "GRANIAN_RELOAD_PATHS",
    "--metrics": "GRANIAN_METRICS_ENABLED",
}
_OPTIONS_WITHOUT_GRANIAN_ENV = {
    "--debug",
    "--pdb",
    "--use-pdb",
    "--create-self-signed-cert",
}


def option(*param_decls: str, cls: type[Option] | None = None, **attrs: Any) -> Callable[[FC], FC]:
    """Create an option with Litestar-first and Granian-fallback environment support."""  # ruff: ignore[docstring-missing-returns]
    attrs["show_envvar"] = True
    if "default" in attrs:
        attrs["show_default"] = _pretty_print_default(attrs["default"])
    long_options = [
        declaration.split("/", maxsplit=1)[0] for declaration in param_decls if declaration.startswith("--")
    ]
    if long_options:
        canonical = long_options[-1]
        if canonical not in _OPTIONS_WITHOUT_GRANIAN_ENV:
            granian_env = _GRANIAN_ENV_OVERRIDES.get(
                canonical,
                f"GRANIAN_{canonical[2:].replace('-', '_').upper()}",
            )
            configured_env = attrs.get("envvar")
            if configured_env is None:
                attrs["envvar"] = granian_env
            else:
                envvars = [configured_env] if isinstance(configured_env, str) else list(configured_env)
                if granian_env not in envvars:
                    envvars.append(granian_env)
                attrs["envvar"] = envvars
    return click_option(*param_decls, cls=cls, **attrs)  # pyright: ignore


@command(name="run", context_settings={"show_default": True}, help="Start application server")
@option(
    "-r",
    "--reload/--no-reload",
    default=False,
    help="Enable auto reload when application files change",
    envvar="LITESTAR_RELOAD",
)
@option(
    "-R",
    "--reload-dir",
    "--reload-paths",
    "reload_paths",
    type=CommaSplittedPath(  # type: ignore[type-var]
        exists=True,
        file_okay=True,
        dir_okay=True,
        readable=True,
        path_type=Path,  # pyright: ignore[reportArgumentType]
    ),
    multiple=True,
    help="Paths to watch for changes; repeatable",
    envvar="LITESTAR_RELOAD_DIRS",
)
@option(
    "-I",
    "--reload-include",
    type=CommaSplittedPath(),
    multiple=True,
    help="Glob patterns for files to include when watching for file changes",
    envvar="LITESTAR_RELOAD_INCLUDES",
)
@option(
    "-E",
    "--reload-exclude",
    type=CommaSplittedPath(),
    multiple=True,
    help="Glob patterns for files to exclude when watching for file changes",
    envvar="LITESTAR_RELOAD_EXCLUDES",
)
@option("-p", "--port", help="Port to bind to", type=int, default=8000, envvar="LITESTAR_PORT")
@option(
    "-W",
    "--wc",
    "--web-concurrency",
    "--workers",
    type=IntRange(min=1),
    default=1,
    help="Number of Granian application workers (processes on GIL builds; threads on free-threaded builds)",
    envvar=["LITESTAR_WEB_CONCURRENCY", "WEB_CONCURRENCY"],
)
@option(
    "-H",
    "--host",
    help="Host address to bind to",
    default="127.0.0.1",
    envvar="LITESTAR_HOST",
)
@option(
    "-F",
    "--fd",
    "--file-descriptor",
    "fd",
    type=int,
    help="Bind to a socket from this file descriptor.",
    envvar="LITESTAR_FILE_DESCRIPTOR",
)
@option(
    "-U",
    "--uds",
    "--unix-domain-socket",
    "uds",
    type=ClickPath(exists=False, writable=True),
    help="Unix Domain Socket path",
    envvar="LITESTAR_UNIX_DOMAIN_SOCKET",
)
@option("-d", "--debug", is_flag=True, help="Run app in debug mode", envvar="LITESTAR_DEBUG")
@option(
    "-P",
    "--pdb",
    "--use-pdb",
    is_flag=True,
    help="Drop into PDB on an exception",
    envvar="LITESTAR_PDB",
)
@option(
    "--ssl-certfile",
    "--ssl-certificate",
    "ssl_certificate",
    type=ClickPath(file_okay=True, exists=False, dir_okay=False, readable=True, path_type=Path),  # type: ignore[type-var]
    help="SSL certificate file (Granian alias: --ssl-certificate)",
    envvar="LITESTAR_SSL_CERT_PATH",
)
@option(
    "--ssl-keyfile",
    type=ClickPath(file_okay=True, exists=False, dir_okay=False, readable=True, path_type=Path),  # type: ignore[type-var]
    help="SSL private key file (PKCS#8 format only)",
    envvar="LITESTAR_SSL_KEY_PATH",
)
@option(
    "--create-self-signed-cert",
    is_flag=True,
    help="If certificate and key are not found at specified locations, create a self-signed certificate and a key",
    envvar="LITESTAR_CREATE_SELF_SIGNED_CERT",
)
@option("--uds-permissions", type=OctalIntType(), help="Unix Domain Socket permissions (octal)")
@option(
    "--http",
    type=_EnumChoice(HTTPModes),
    default=HTTPModes.auto,
    help="HTTP version to use: auto, HTTP/1, or HTTP/2",
)
@option("--blocking-threads", type=IntRange(1), help="Number of blocking threads (per worker)")
@option(
    "--blocking-threads-idle-timeout",
    type=Duration(5, 600),
    default=30,
    help=(
        "The maximum amount of time an idle blocking thread will be kept alive "
        "(supports human-readable format like '5m', '30s')"
    ),
)
@option(
    "--runtime-threads",
    type=IntRange(1),
    default=1,
    help="Number of Rust network I/O threads per worker; does not control Python application parallelism",
)
@option(
    "--runtime-blocking-threads",
    type=IntRange(1),
    help="Number of runtime I/O blocking threads (per worker)",
)
@option(
    "--runtime-mode",
    type=_EnumChoice(RuntimeModes),
    default=RuntimeModes.auto,
    help="Granian Rust runtime mode (single/multi-threaded/auto-detect); ASGI auto resolves to multi-threaded",
)
@option("--loop", type=_EnumChoice(Loops), default=Loops.auto, help="Event loop implementation")
@option("--task-impl", type=_EnumChoice(TaskImpl), default=TaskImpl.asyncio, help="Async task implementation to use")
@option(
    "--backlog",
    type=IntRange(128),
    default=1024,
    help="Maximum number of connections to hold in backlog (globally)",
)
@option(
    "--backpressure",
    type=IntRange(1),
    show_default="backlog/workers",
    help="Maximum number of requests to process concurrently (per worker)",
)
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
    default=HTTP1Settings.keep_alive,
    help="Enables or disables HTTP/1 keep-alive",
)
@option(
    "--http1-pipeline-flush/--no-http1-pipeline-flush",
    default=HTTP1Settings.pipeline_flush,
    help="Aggregates HTTP/1 flushes to better support pipelined responses (experimental)",
)
@option(
    "--http2-adaptive-window/--no-http2-adaptive-window",
    default=HTTP2Settings.adaptive_window,
    help="Sets whether to use an adaptive flow control for HTTP2",
)
@option(
    "--http2-initial-connection-window-size",
    type=IntRange(1024),
    default=HTTP2Settings.initial_connection_window_size,
    help="Sets the max connection-level flow control for HTTP2",
)
@option(
    "--http2-initial-stream-window-size",
    type=IntRange(1024),
    default=HTTP2Settings.initial_stream_window_size,
    help="Sets the `SETTINGS_INITIAL_WINDOW_SIZE` option for HTTP2 stream-level flow control",
)
@option(
    "--http2-keep-alive-interval",
    type=IntRange(1, 60_000),
    help="Sets the interval (in milliseconds) between HTTP/2 keep-alive pings",
)
@option(
    "--http2-keep-alive-timeout",
    type=Duration(1),
    default=HTTP2Settings.keep_alive_timeout,
    help=(
        "Sets a timeout for receiving an acknowledgement of the HTTP2 keep-alive ping "
        "(supports human-readable format like '20s')"
    ),
)
@option(
    "--http2-max-concurrent-streams",
    type=IntRange(10),
    default=HTTP2Settings.max_concurrent_streams,
    help="Sets the SETTINGS_MAX_CONCURRENT_STREAMS option for HTTP2 connections",
)
@option(
    "--http2-max-frame-size",
    type=IntRange(1024),
    default=HTTP2Settings.max_frame_size,
    help="Sets the maximum frame size to use for HTTP2",
)
@option(
    "--http2-max-headers-size",
    type=IntRange(1),
    default=HTTP2Settings.max_headers_size,
    help="Sets the max size of received header frames",
)
@option(
    "--http2-max-send-buffer-size",
    type=IntRange(1024),
    default=HTTP2Settings.max_send_buffer_size,
    help="Set the maximum write buffer size for each HTTP/2 stream",
)
@option("--granian-log/--granian-no-log", "log_enabled", default=True, help="Enable logging")
@option(
    "--granian-log-level",
    "log_level",
    type=_EnumChoice(LogLevels),
    default=LogLevels.info,
    help="Log level",
)
@option(
    "--granian-access-log/--granian-no-access-log",
    "log_access_enabled",
    default=False,
    help="Enable access log",
)
@option("--granian-access-log-fmt", "log_access_fmt", help="Access log format")
@option("--ssl-keyfile-password", help="SSL key password")
@option(
    "--ssl-protocol-min",
    type=_EnumChoice(SSLProtocols),
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
    multiple=True,
    help="SSL CRL file(s)",
)
@option(
    "--ssl-client-verify/--no-ssl-client-verify",
    default=False,
    help="Verify clients SSL certificates",
)
@option("--url-path-prefix", help="URL path prefix the app is mounted on")
@option(
    "--respawn-failed-workers/--no-respawn-failed-workers",
    default=False,
    help="Enable workers respawn on unexpected exit",
)
@option("--respawn-interval", default=3.5, help="The number of seconds to sleep between workers respawn")
@option(
    "--workers-lifetime",
    type=Duration(60),
    help=(
        "The maximum amount of time a worker will be kept alive before respawn "
        "(supports human-readable format like '6h', '30m')"
    ),
)
@option(
    "--workers-kill-timeout",
    type=Duration(1, 1800),
    default=5,
    help="Granian worker shutdown timeout; the parent deadline adds five seconds",
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
@option(
    "--reload-ignore-dirs",
    multiple=True,
    help=("Names of directories to ignore. Extends the default directory list in watchfiles' default filter"),
)
@option(
    "--reload-ignore-patterns",
    multiple=True,
    help=(
        "File/directory name patterns (regex) to ignore changes for. Extends the "
        "default list of patterns to ignore in watchfiles' default filter"
    ),
)
@option(
    "--reload-ignore-paths",
    type=ClickPath(exists=False, path_type=Path),  # type: ignore[type-var]
    multiple=True,
    help="Absolute paths to ignore changes for",
)
@option(
    "--reload-tick",
    type=IntRange(50, 5000),
    default=50,
    help="The tick frequency (in milliseconds) the reloader watch for changes",
)
@option(
    "--reload-ignore-worker-failure/--no-reload-ignore-worker-failure",
    default=False,
    help="Ignore worker failures when auto reload is enabled",
)
@option("--process-name", help="Set a custom name for Granian processes")
@option(
    "--pid-file",
    type=ClickPath(exists=False, file_okay=True, dir_okay=False, writable=True, path_type=Path),  # type: ignore[type-var]
    help="A path to write the PID file to",
)
@option("--ws/--no-ws", "ws_enabled", default=True, help="Enable or disable WebSocket handling")
@option(
    "--static-path-route",
    multiple=True,
    help=(
        "URL route prefix for Granian-served static files. Repeat for multi-mount; "
        "paired positionally with --static-path-mount."
    ),
)
@option(
    "--static-path-mount",
    type=ClickPath(exists=True, file_okay=False, dir_okay=True, readable=True, path_type=Path),  # type: ignore[type-var]
    multiple=True,
    help=(
        "Directory path for Granian to serve static files from. Repeat for multi-mount; "
        "paired positionally with --static-path-route."
    ),
)
@option(
    "--static-path-dir-to-file",
    help=(
        "Filename to serve for directory requests under a static mount (e.g. "
        "'index.html'). Enables HTML mode for SPA-style serving."
    ),
)
@option(
    "--static-path-expires",
    type=Duration(0),
    default=86400,
    help=(
        "Cache expiration for Granian static files (supports human-readable format "
        "like '1d', '1h'). Pass 0 to disable caching."
    ),
)
@option(
    "--working-dir",
    type=ClickPath(exists=True, file_okay=False, dir_okay=True, readable=True, path_type=Path),  # type: ignore[type-var]
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
    help="Explicit Granian JSON dictConfig; completely overrides automatic formatter matching",
)
@option(
    "--metrics/--no-metrics",
    "metrics_enabled",
    default=False,
    help="Enable Granian's built-in Prometheus metrics endpoint.",
)
@option(
    "--metrics-scrape-interval",
    type=Duration(1, 60),
    default=15,
    help="Metrics sample interval (supports human-readable format like '15s', '1m').",
)
@option("--metrics-address", default="127.0.0.1", help="Address to bind the metrics endpoint to.")
@option("--metrics-port", type=IntRange(1, 65535), default=9090, help="Port to bind the metrics endpoint to.")
@option(
    "--in-subprocess/--no-subprocess",
    default=None,
    help="Deprecated compatibility option; supervised execution is always used.",
    envvar="LITESTAR_GRANIAN_IN_SUBPROCESS",
)
@option(
    "--use-litestar-logger/--no-litestar-logger",
    default=None,
    help="Deprecated compatibility option; formatter matching is automatic.",
    envvar="LITESTAR_GRANIAN_USE_LITESTAR_LOGGER",
)
def run_command(
    app: "Litestar",
    host: str,
    port: int,
    fd: int | None,
    uds: str | None,
    uds_permissions: int | None,
    http: HTTPModes,
    wc: int,
    blocking_threads: int | None,
    blocking_threads_idle_timeout: int,
    runtime_threads: int,
    runtime_blocking_threads: int | None,
    runtime_mode: RuntimeModes,
    loop: Loops,
    task_impl: TaskImpl,
    backlog: int,
    backpressure: int | None,
    http1_buffer_size: int,
    http1_header_read_timeout: int,
    http1_keep_alive: bool,
    http1_pipeline_flush: bool,
    http2_adaptive_window: bool,
    http2_initial_connection_window_size: int,
    http2_initial_stream_window_size: int,
    http2_keep_alive_interval: int | None,
    http2_keep_alive_timeout: int,
    http2_max_concurrent_streams: int,
    http2_max_frame_size: int,
    http2_max_headers_size: int,
    http2_max_send_buffer_size: int,
    log_enabled: bool,
    log_access_enabled: bool,
    log_access_fmt: str | None,
    log_level: LogLevels,
    ssl_certificate: Path | None,
    ssl_keyfile: Path | None,
    ssl_keyfile_password: str | None,
    ssl_protocol_min: SSLProtocols,
    ssl_ca: Path | None,
    ssl_crl: tuple[Path, ...],
    ssl_client_verify: bool,
    create_self_signed_cert: bool,
    url_path_prefix: str | None,
    respawn_failed_workers: bool,
    respawn_interval: float,
    workers_lifetime: int | None,
    workers_kill_timeout: int,
    workers_max_rss: int | None,
    rss_sample_interval: int,
    rss_samples: int,
    reload: bool,
    reload_paths: tuple[Path, ...],
    reload_include: tuple[str, ...],
    reload_exclude: tuple[str, ...],
    reload_ignore_dirs: tuple[str, ...],
    reload_ignore_patterns: tuple[str, ...],
    reload_ignore_paths: tuple[Path, ...],
    reload_tick: int,
    reload_ignore_worker_failure: bool,
    process_name: str | None,
    pid_file: Path | None,
    static_path_route: tuple[str, ...],
    static_path_mount: tuple[Path, ...],
    static_path_dir_to_file: str | None,
    static_path_expires: int,
    ws_enabled: bool,
    debug: bool,
    pdb: bool,
    in_subprocess: bool | None,
    use_litestar_logger: bool | None,
    working_dir: Path | None,
    env_files: tuple[Path, ...],
    log_config: Path | None,
    metrics_enabled: bool,
    metrics_scrape_interval: int,
    metrics_address: str,
    metrics_port: int,
    ctx: Context,
) -> None:
    """Run a Litestar application under a supervised Granian process group.

    The Litestar parent owns server lifespans and signal forwarding. One fresh
    Granian child group owns ASGI workers and returns its normalized exit
    status to this command.
    """  # ruff: ignore[docstring-missing-exception]
    reload = reload or bool(reload_paths) or bool(reload_include) or bool(reload_exclude)
    _validate_cli_options(
        fd=fd,
        reload=reload,
        workers_max_rss=workers_max_rss,
        ssl_client_verify=ssl_client_verify,
        ssl_ca=ssl_ca,
        static_path_route=static_path_route,
        static_path_mount=static_path_mount,
    )
    _warn_deprecated_compatibility_options(
        in_subprocess=in_subprocess,
        use_litestar_logger=use_litestar_logger,
    )
    if callable(ctx.obj):
        ctx.obj = ctx.obj()
    env: LitestarEnv = ctx.obj
    if debug:
        app.debug = True
        env.app.debug = True
        os.environ["LITESTAR_DEBUG"] = "1"
    if pdb:
        app.pdb_on_exception = True
        env.app.pdb_on_exception = True
        os.environ["LITESTAR_PDB"] = "1"

    _warn_if_only_granian_metrics(env.app, metrics_enabled=metrics_enabled)

    if create_self_signed_cert:
        cert, key = create_ssl_files(str(ssl_certificate), str(ssl_keyfile), host)
        if ssl_certificate is None and cert is not None:
            ssl_certificate = Path(cert)
        if ssl_keyfile is None and key is not None:
            ssl_keyfile = Path(key)

    if not (os.getenv("LITESTAR_QUIET_CONSOLE") or False) and isatty():
        console.rule("Starting [blue]Granian[/] supervisor", align="left")
        show_app_info(env.app)

    options = locals().copy()
    options.pop("app")
    options.pop("ctx")
    options.pop("env")
    options.pop("in_subprocess")
    options.pop("use_litestar_logger")
    built_command = _build_granian_command(env, options)
    exit_code = _run_supervised(
        env,
        built_command,
        workers_kill_timeout=workers_kill_timeout,
        port=port,
    )

    console.print("[yellow]Granian workers stopped.[/]")
    if exit_code:
        raise Exit(exit_code)


def _run_supervised(
    env: LitestarEnv,
    built_command: Any,
    *,
    workers_kill_timeout: int,
    port: int,
) -> int:
    with ExitStack() as stack:
        stack.callback(built_command.cleanup)
        supervisor = _GranianSupervisor(
            built_command.argv,
            kill_timeout=workers_kill_timeout,
            environment=built_command.environment,
            pass_fds=built_command.pass_fds,
        )
        signal_forwarder = _SignalForwarder(supervisor)
        previous_app = os.environ.get("LITESTAR_APP")
        had_app = "LITESTAR_APP" in os.environ
        previous_port = os.environ.get("LITESTAR_PORT")
        had_port = "LITESTAR_PORT" in os.environ
        os.environ["LITESTAR_APP"] = env.app_path
        os.environ["LITESTAR_PORT"] = str(port)
        stack.callback(_restore_environment, "LITESTAR_APP", had_app, previous_app)
        stack.callback(_restore_environment, "LITESTAR_PORT", had_port, previous_port)
        stack.callback(signal_forwarder.restore)
        stack.enter_context(_server_lifespan(env.app))
        signal_forwarder.install()
        return supervisor.run()


def _is_free_threaded_build() -> bool:
    return bool(sysconfig.get_config_var("Py_GIL_DISABLED") == 1)


def _validate_cli_options(
    *,
    fd: int | None,
    reload: bool,
    workers_max_rss: int | None,
    ssl_client_verify: bool,
    ssl_ca: Path | None,
    static_path_route: tuple[str, ...],
    static_path_mount: tuple[Path, ...],
) -> None:
    if _is_free_threaded_build():
        if reload:
            message = "--reload is not supported on free-threaded Python"
            raise UsageError(message)
        if workers_max_rss is not None:
            message = "--workers-max-rss is not supported on free-threaded Python"
            raise UsageError(message)
    if fd is not None and sys.platform == "win32":
        message = "--fd is not supported on Windows"
        raise UsageError(message)
    if ssl_client_verify and ssl_ca is None:
        message = "--ssl-client-verify requires --ssl-ca"
        raise UsageError(message)
    if len(static_path_route) != len(static_path_mount):
        message = "--static-path-route and --static-path-mount counts must match"
        raise UsageError(message)


def _warn_deprecated_compatibility_options(
    *,
    in_subprocess: bool | None,
    use_litestar_logger: bool | None,
) -> None:
    if in_subprocess is not None:
        console.print(
            "[yellow]Warning:[/] --in-subprocess/--no-subprocess is deprecated and ignored; "
            "supervised execution is always used."
        )
    if use_litestar_logger is not None:
        console.print(
            "[yellow]Warning:[/] --use-litestar-logger/--no-litestar-logger is deprecated and ignored; "
            "Granian formatting now matches Litestar automatically. Use --log-config for a complete override."
        )


def _warn_if_only_granian_metrics(app: "Litestar", *, metrics_enabled: bool) -> None:
    if metrics_enabled and not _has_litestar_prometheus_instrumentation(app):
        console.print(
            "[yellow]Warning:[/] --metrics enables Granian server and worker metrics only. "
            "No Litestar Prometheus middleware was detected, so application-level request metrics "
            "are not being exported."
        )


def _has_litestar_prometheus_instrumentation(app: "Litestar") -> bool:
    for definition in app.middleware:
        middleware = getattr(definition, "middleware", definition)
        if isinstance(middleware, tuple):
            middleware = middleware[0]
        if _is_litestar_prometheus_type(middleware, {"PrometheusMiddleware"}):
            return True
    return any(_is_litestar_prometheus_type(plugin, {"PrometheusPlugin"}) for plugin in app.plugins)


def _is_litestar_prometheus_type(value: object, names: set[str]) -> bool:
    value_type = value if isinstance(value, type) else type(value)
    return any(
        base.__name__ in names
        and base.__module__.startswith(("litestar.plugins.prometheus", "litestar.contrib.prometheus"))
        for base in value_type.__mro__
    )


def _restore_environment(name: str, existed: bool, previous: str | None) -> None:
    if existed and previous is not None:
        os.environ[name] = previous
    else:
        os.environ.pop(name, None)
