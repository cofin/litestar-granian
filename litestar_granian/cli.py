from __future__ import annotations

import multiprocessing
import os
import subprocess  # noqa: S404
import sys
from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from rich_click import Context, IntRange, command, option
    from rich_click import Path as ClickPath
except ImportError:
    from click import Context, IntRange, command, option  # type: ignore[no-redef]
    from click import Path as ClickPath
from granian import Granian
from granian._loops import loops  # noqa: PLC2701
from granian.constants import HTTPModes, Interfaces, Loops, ThreadModes
from granian.errors import FatalError
from granian.http import HTTP1Settings, HTTP2Settings
from granian.log import LogLevels
from litestar.cli._utils import (  # pyright: ignore[reportPrivateUsage]
    LitestarEnv,
    console,  # noqa: PLC2701
    create_ssl_files,  # noqa: PLC2701
    show_app_info,  # noqa: PLC2701
)
from litestar.cli.commands.core import _server_lifespan  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
from litestar.logging import LoggingConfig

from litestar_granian.manager import ProcessManager

try:
    from litestar.cli._utils import isatty  # type: ignore[attr-defined,unused-ignore]
except ImportError:  # pragma: nocover

    def isatty() -> bool:  # pragma: nocover
        """Detect if a terminal is TTY enabled.

        This was added in Litestar 2.8 and is back-ported for compatibility.

        This is a convenience wrapper around the built in system methods.  This allows for easier testing of TTY/non-TTY modes.

        Returns:
            bool - True of the terminal is TTY enabled
        """
        return sys.stdout.isatty()


if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.cli._utils import LitestarEnv


@command(name="run", context_settings={"show_default": True}, help="Start application server")
# Server configuration
@option("-H", "--host", help="Server under this host", default="127.0.0.1", show_default=True, envvar="LITESTAR_HOST")
@option("-p", "--port", help="Serve under this port", type=int, default=8000, show_default=True, envvar="LITESTAR_PORT")
@option("-d", "--debug", help="Run app in debug mode", is_flag=True, envvar="LITESTAR_DEBUG")
@option("-P", "--pdb", "--use-pdb", help="Drop into PDB on an exception", is_flag=True, envvar="LITESTAR_PDB")
@option("--url-path-prefix", help="URL path prefix the app is mounted on", default=None, show_default=False)
# Process & Threading configuration
@option(
    "-W",
    "--wc",
    "--web-concurrency",
    "--workers",
    help="The number of processes to start.",
    type=IntRange(min=1, max=multiprocessing.cpu_count() + 1),
    show_default=True,
    default=1,
    envvar=["LITESTAR_WEB_CONCURRENCY", "WEB_CONCURRENCY"],
)
@option(
    "--threads",
    help="The number of threads.",
    type=IntRange(min=1),
    show_default=True,
    default=1,
)
@option(
    "--blocking-threads",
    help="The number of blocking threads.",
    type=IntRange(min=1),
    show_default=True,
    default=1,
)
@option("--threading-mode", help="Threading mode to use.", type=ThreadModes, default=ThreadModes.workers.value)
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
@option("--http", help="HTTP Version to use (HTTP or HTTP2)", type=HTTPModes, default=HTTPModes.auto.value)
@option(
    "--http1-buffer-size",
    help="Set the maximum buffer size for HTTP/1 connections",
    type=IntRange(min=8192),
    show_default=True,
    default=HTTP1Settings.max_buffer_size,
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
    help="Sets a timeout for receiving an acknowledgement of the HTTP2 keep-alive ping",
    type=int,
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
# SSL configuration
@option(
    "--ssl-keyfile",
    type=ClickPath(file_okay=True, exists=True, dir_okay=False, readable=True),
    help="SSL key file",
    default=None,
    show_default=False,
)
@option(
    "--ssl-certificate",
    type=ClickPath(file_okay=True, exists=True, dir_okay=False, readable=True),
    help="SSL certificate file",
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
# Logging configuration
@option("--log/--no-log", "log_enabled", default=True, help="Enable logging")
@option("--access-log/--no-access-log", "log_access_enabled", default=False, help="Enable access log")
@option("--access-log-fmt", "log_access_fmt", help="Access log format")
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
    type=IntRange(60),
    help="The maximum amount of time in seconds a worker will be kept alive before respawn",
)
@option(
    "--workers-kill-timeout",
    type=IntRange(1, 1800),
    help="The amount of time in seconds to wait for killing workers that refused to gracefully stop",
    show_default="disabled",
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
    type=ClickPath(exists=True, file_okay=True, dir_okay=True, readable=True, path_type=Path),  # type: ignore[type-var]
    help="Paths to watch for changes",
    show_default="Working directory",
    multiple=True,
)
@option(
    "--reload-ignore-dirs",
    help=(
        "Names of directories to ignore changes for. "
        "Extends the default list of directories to ignore in watchfiles' default filter"
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
@option(
    "--in-subprocess/--no-subprocess",
    "in_subprocess",
    default=True,
    help="Launch Granian in a subprocess.",
    envvar="LITESTAR_GRANIAN_IN_SUBPROCESS",
)
def run_command(
    app: Litestar,
    reload: bool,
    reload_paths: list[Path] | None,
    reload_ignore_dirs: list[str] | None,
    reload_ignore_patterns: list[str] | None,
    reload_ignore_paths: list[Path] | None,
    host: str,
    port: int,
    wc: int,
    threads: int,
    blocking_threads: int,
    respawn_failed_workers: bool,
    respawn_interval: float,
    workers_lifetime: int | None,
    workers_kill_timeout: int | None,
    http1_keep_alive: bool,
    http1_buffer_size: int,
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
    http: HTTPModes,
    log_access_enabled: bool,
    log_access_fmt: str | None,
    log_enabled: bool,
    backlog: int,
    backpressure: int | None,
    threading_mode: ThreadModes,
    ssl_keyfile: Path | None,
    ssl_certificate: Path | None,
    ssl_keyfile_password: str | None,
    create_self_signed_cert: bool,
    url_path_prefix: str | None,
    process_name: str | None,
    pid_file: Path | None,
    debug: bool,
    pdb: bool,
    in_subprocess: bool,
    ctx: Context,
) -> None:  # sourcery skip: low-code-quality
    """Run a Litestar app.

    The app can be either passed as a module path in the form of <module name>.<submodule>:<app instance or factory>,
    set as an environment variable LITESTAR_APP with the same format or automatically discovered from one of these
    canonical paths: app.py, asgi.py, application.py or app/__init__.py. When auto-discovering application factories,
    functions with the name ``create_app`` are considered, or functions that are annotated as returning a ``Litestar``
    instance.
    """

    loops.get("auto")
    if reload:
        # code fails to fully reload unless this is set to true
        in_subprocess = True
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
    threading_mode = threading_mode or ThreadModes.workers
    workers = wc
    if create_self_signed_cert:
        cert, key = create_ssl_files(str(ssl_certificate), str(ssl_keyfile), host)
        ssl_certificate = ssl_certificate or Path(cert) if cert is not None else None  # pyright: ignore[reportUnnecessaryComparison]
        ssl_keyfile = ssl_keyfile or Path(key) if key is not None else None  # pyright: ignore[reportUnnecessaryComparison]

    if not quiet_console and isatty():
        console.rule("[yellow]Starting [blue]Granian[/] server process[/]", align="left")
        show_app_info(env.app)
    with _server_lifespan(env.app):
        if in_subprocess:
            _run_granian_in_subprocess(
                env=env,
                reload=reload,
                reload_paths=reload_paths,
                reload_ignore_dirs=reload_ignore_dirs,
                reload_ignore_patterns=reload_ignore_patterns,
                reload_ignore_paths=reload_ignore_paths,
                port=port,
                wc=workers,
                workers_lifetime=workers_lifetime,
                threads=threads,
                http=http,
                backlog=backlog,
                backpressure=backpressure,
                blocking_threads=blocking_threads,
                respawn_failed_workers=respawn_failed_workers,
                respawn_interval=respawn_interval,
                workers_kill_timeout=workers_kill_timeout,
                log_access_enabled=log_access_enabled,
                log_access_fmt=log_access_fmt,
                log_enabled=log_enabled,
                http1_buffer_size=http1_buffer_size,
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
                threading_mode=threading_mode,
                process_name=process_name,
                pid_file=pid_file,
                ssl_keyfile=ssl_keyfile,
                ssl_certificate=ssl_certificate,
                ssl_keyfile_password=ssl_keyfile_password,
                url_path_prefix=url_path_prefix,
                host=host,
            )
        else:
            _run_granian(
                env=env,
                reload=reload,
                reload_paths=reload_paths,
                reload_ignore_dirs=reload_ignore_dirs,
                reload_ignore_patterns=reload_ignore_patterns,
                reload_ignore_paths=reload_ignore_paths,
                port=port,
                wc=workers,
                workers_lifetime=workers_lifetime,
                threads=threads,
                http=http,
                backlog=backlog,
                backpressure=backpressure,
                blocking_threads=blocking_threads,
                respawn_failed_workers=respawn_failed_workers,
                respawn_interval=respawn_interval,
                workers_kill_timeout=workers_kill_timeout,
                log_access_enabled=log_access_enabled,
                log_access_fmt=log_access_fmt,
                log_enabled=log_enabled,
                http1_buffer_size=http1_buffer_size,
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
                threading_mode=threading_mode,
                process_name=process_name,
                pid_file=pid_file,
                ssl_keyfile=ssl_keyfile,
                ssl_certificate=ssl_certificate,
                url_path_prefix=url_path_prefix,
                ssl_keyfile_password=ssl_keyfile_password,
                host=host,
            )


def _run_granian(
    env: LitestarEnv,
    host: str,
    port: int,
    wc: int,
    threads: int,
    http: HTTPModes,
    backlog: int,
    backpressure: int | None,
    blocking_threads: int,
    respawn_failed_workers: bool,
    respawn_interval: float,
    workers_kill_timeout: int | None,
    log_access_enabled: bool,
    log_access_fmt: str | None,
    log_enabled: bool,
    http1_buffer_size: int,
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
    threading_mode: ThreadModes,
    workers_lifetime: int | None,
    reload: bool,
    reload_paths: list[Path] | None,
    reload_ignore_dirs: list[str] | None,
    reload_ignore_patterns: list[str] | None,
    reload_ignore_paths: list[Path] | None,
    process_name: str | None,
    pid_file: Path | None,
    ssl_keyfile: Path | None,
    ssl_certificate: Path | None,
    ssl_keyfile_password: str | None,
    url_path_prefix: str | None,
) -> None:
    import signal
    from functools import partial

    def handle_sigterm(server: Granian, signum: int, frame: Any) -> None:
        """Handle SIGTERM/SIGINT gracefully."""
        try:
            server.shutdown()  # type: ignore[no-untyped-call]
        finally:
            console.print("[yellow]Granian process stopped.[/]")
            sys.exit(0)

    if env.app.logging_config is not None and isinstance(env.app.logging_config, LoggingConfig):
        if env.app.logging_config.loggers.get("_granian", None) is None:
            env.app.logging_config.loggers.update(
                {"_granian": {"level": "INFO", "handlers": ["queue_listener"], "propagate": False}},
            )
        env.app.logging_config.configure()
    excluded_fields = {"configure_root_logger", "incremental"}
    log_dictconfig = (
        {
            _field.name: getattr(env.app.logging_config, _field.name)
            for _field in fields(env.app.logging_config)  # type: ignore[arg-type]
            if getattr(env.app.logging_config, _field.name) is not None and _field.name not in excluded_fields
        }
        if env.app.logging_config is not None
        else None
    )
    if log_dictconfig is not None:
        log_dictconfig["version"] = 1
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
            keep_alive=http1_keep_alive,
            max_buffer_size=http1_buffer_size,
            pipeline_flush=http1_pipeline_flush,
        )
        http2_settings = None

    server = Granian(
        env.app_path,
        factory=env.is_app_factory,
        address=host,
        port=port,
        interface=Interfaces.ASGI,
        workers=wc,
        workers_lifetime=workers_lifetime,
        threads=threads,
        blocking_threads=blocking_threads,
        threading_mode=threading_mode,
        loop=Loops.auto,
        http=http,
        websockets=http.value != HTTPModes.http2.value,
        backlog=backlog,
        backpressure=backpressure,
        http1_settings=http1_settings,
        http2_settings=http2_settings,
        ssl_cert=ssl_certificate,
        ssl_key=ssl_keyfile,
        ssl_key_password=ssl_keyfile_password,
        url_path_prefix=url_path_prefix,
        respawn_failed_workers=respawn_failed_workers,
        respawn_interval=respawn_interval,
        workers_kill_timeout=workers_kill_timeout,
        reload=reload,
        reload_paths=reload_paths,
        reload_ignore_dirs=reload_ignore_dirs,
        reload_ignore_patterns=reload_ignore_patterns,
        reload_ignore_paths=reload_ignore_paths,
        process_name=process_name,
        pid_file=pid_file,
        log_enabled=log_enabled,
        log_access=log_access_enabled,
        log_access_format=log_access_fmt,
        log_level=LogLevels.info,
        log_dictconfig=log_dictconfig,
    )

    # Set up signal handlers
    signal.signal(signal.SIGTERM, partial(handle_sigterm, server))
    signal.signal(signal.SIGINT, partial(handle_sigterm, server))

    process_manager = ProcessManager(
        server=server, shutdown_callback=lambda: console.print("[yellow]Shutdown complete.[/]")
    )

    process_manager.run()


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
    env: LitestarEnv,
    host: str,
    port: int,
    wc: int,
    threads: int,
    http: HTTPModes,
    backlog: int,
    backpressure: int | None,
    blocking_threads: int,
    respawn_failed_workers: bool,
    respawn_interval: float,
    log_access_enabled: bool,
    log_access_fmt: str | None,
    log_enabled: bool,
    http1_buffer_size: int,
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
    threading_mode: ThreadModes,
    workers_lifetime: int | None,
    workers_kill_timeout: int | None,
    reload: bool,
    reload_paths: list[Path] | None,
    reload_ignore_dirs: list[str] | None,
    reload_ignore_patterns: list[str] | None,
    reload_ignore_paths: list[Path] | None,
    process_name: str | None,
    pid_file: Path | None,
    ssl_keyfile: Path | None,
    ssl_certificate: Path | None,
    ssl_keyfile_password: str | None,
    url_path_prefix: str | None,
) -> None:
    process_args: dict[str, Any] = {
        "reload": reload,
        "host": host,
        "port": port,
        "interface": Interfaces.ASGI.value,
        "http": http.value,
        "threads": threads,
        "workers": wc,
        "threading-mode": threading_mode.value,
        "blocking-threads": blocking_threads,
        "loop": Loops.auto.value,
        "respawn-failed-workers": respawn_failed_workers,
        "respawn-interval": respawn_interval,
        "backlog": backlog,
    }
    if env.is_app_factory:
        process_args["factory"] = env.is_app_factory
    if reload_paths:
        process_args["reload-paths"] = (Path(d).absolute for d in reload_paths)
    if reload_ignore_dirs:
        process_args["reload-ignore-dirs"] = reload_ignore_dirs
    if reload_ignore_patterns:
        process_args["reload-ignore-patterns"] = reload_ignore_patterns
    if reload_ignore_paths:
        process_args["reload-ignore-paths"] = (Path(d).absolute for d in reload_ignore_paths)
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
    if not log_enabled:
        process_args["no-log"] = True
    if http.value in {HTTPModes.http1.value, HTTPModes.auto.value}:
        process_args["http1-keep-alive"] = http1_keep_alive
        process_args["http1-buffer-size"] = http1_buffer_size
        process_args["http1-pipeline-flush"] = http1_pipeline_flush
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
        # websockets aren't supported in http2 only?
        process_args["websockets"] = False
    if url_path_prefix is not None:
        process_args["url-path-prefix"] = url_path_prefix
    if ssl_certificate is not None:
        process_args["ssl-certificate"] = ssl_certificate
    if ssl_keyfile is not None:
        process_args["ssl-keyfile"] = ssl_keyfile
    if ssl_keyfile_password is not None:
        process_args["ssl-keyfile-password"] = ssl_keyfile_password
    if process_name is not None:
        process_args["process-name"] = process_name
    if pid_file is not None:
        process_args["pid-file"] = Path(pid_file).absolute
    try:
        subprocess.run(
            [sys.executable, "-m", "granian", env.app_path, *_convert_granian_args(process_args)],
            check=True,
        )
    except KeyboardInterrupt:
        sys.exit(1)
    except FatalError:
        sys.exit(1)
    finally:
        console.print("[yellow]Granian process stopped.[/]")
