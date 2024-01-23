from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import TYPE_CHECKING

import click
from click import Context, command, option
from granian.constants import HTTPModes, ThreadModes
from granian.http import HTTP1Settings, HTTP2Settings

if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.cli._utils import LitestarEnv


@command(name="run")
@option("-p", "--port", help="Serve under this port", type=int, default=8000, show_default=True)
@option(
    "-W",
    "--wc",
    "--web-concurrency",
    "--workers",
    help="The number of processes to start.",
    type=click.IntRange(min=1, max=multiprocessing.cpu_count() + 1),
    show_default=True,
    default=1,
)
@option(
    "--threads",
    help="The number of threads.",
    type=click.IntRange(min=1),
    show_default=True,
    default=1,
)
@option(
    "--blocking-threads",
    help="The number of blocking threads.",
    type=click.IntRange(min=1),
    show_default=True,
    default=1,
)
@option("--threading-mode", help="Threading mode to use.", type=ThreadModes, default=ThreadModes.workers)
@option("--http", help="HTTP Version to use (HTTP or HTTP2)", default=HTTPModes.auto, show_default=True)
@option("--no-opt", help="Disable event loop optimizations", is_flag=True, default=False)
@option(
    "--backlog",
    help="Maximum number of connections to hold in backlog.",
    type=click.IntRange(min=128),
    show_default=True,
    default=1024,
)
@option("-H", "--host", help="Server under this host", default="127.0.0.1", show_default=True)
@option(
    "--ssl-keyfile",
    type=click.Path(file_okay=True, exists=True, dir_okay=False, readable=True),
    help="SSL key file",
    default=None,
    show_default=False,
)
@option(
    "--ssl-certificate",
    type=click.Path(file_okay=True, exists=True, dir_okay=False, readable=True),
    help="SSL certificate file",
    default=None,
    show_default=False,
)
@option(
    "--create-self-signed-cert",
    help="If certificate and key are not found at specified locations, create a self-signed certificate and a key",
    is_flag=True,
)
@option(
    "--http1-buffer-size",
    help="Set the maximum buffer size for HTTP/1 connections",
    type=click.IntRange(min=8192),
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
    show_default=False,
    default=HTTP2Settings.keep_alive_interval,
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
@option("--url-path-prefix", help="URL path prefix the app is mounted on", default=None, show_default=False)
@option("-d", "--debug", help="Run app in debug mode", is_flag=True)
@option("-P", "--pdb", "--use-pdb", help="Drop into PDB on an exception", is_flag=True)
@option(
    "--respawn-failed-workers/--no-respawn-failed-workers",
    help="Enable workers respawn on unexpected exit",
    default=False,
    is_flag=True,
)
@option("-r", "--reload", help="Reload server on changes", default=False, is_flag=True)
def run_command(
    app: Litestar,
    reload: bool,
    port: int,
    wc: int,
    threads: int,
    blocking_threads: int,
    respawn_failed_workers: bool,
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
    no_opt: bool,
    backlog: int,
    threading_mode: ThreadModes,
    ssl_keyfile: Path | None,
    ssl_certificate: Path | None,
    create_self_signed_cert: bool,
    url_path_prefix: str | None,
    host: str,
    debug: bool,
    pdb: bool,
    ctx: Context,
) -> None:  # sourcery skip: low-code-quality
    """Run a Litestar app.

    The app can be either passed as a module path in the form of <module name>.<submodule>:<app instance or factory>,
    set as an environment variable LITESTAR_APP with the same format or automatically discovered from one of these
    canonical paths: app.py, asgi.py, application.py or app/__init__.py. When auto-discovering application factories,
    functions with the name ``create_app`` are considered, or functions that are annotated as returning a ``Litestar``
    instance.
    """
    import os

    from granian.constants import ThreadModes
    from litestar.cli._utils import create_ssl_files

    if debug is not None:
        app.debug = True
        os.environ["LITESTAR_DEBUG"] = "1"
    if pdb:
        os.environ["LITESTAR_PDB"] = "1"

    if callable(ctx.obj):
        ctx.obj = ctx.obj()
    else:
        if debug:
            ctx.obj.app.debug = True
        if pdb:
            ctx.obj.app.pdb_on_exception = True

    env: LitestarEnv = ctx.obj

    threading_mode = threading_mode or ThreadModes.workers
    host = env.host or host
    port = env.port if env.port is not None else port
    reload = env.reload or reload
    workers = env.web_concurrency or wc
    ssl_certificate = ssl_certificate or Path(env.certfile_path) if env.certfile_path is not None else None
    ssl_keyfile = ssl_keyfile or Path(env.keyfile_path) if env.keyfile_path is not None else None
    create_self_signed_cert = create_self_signed_cert or env.create_self_signed_cert
    if create_self_signed_cert:
        _cert, _key = create_ssl_files(str(ssl_certificate), str(ssl_keyfile), host)
        ssl_certificate = ssl_certificate or Path(_cert) if _cert is not None else None
        ssl_keyfile = ssl_keyfile or Path(_key) if _key is not None else None

    _run(
        env=env,
        reload=reload,
        port=port,
        wc=workers,
        threads=threads,
        http=http,
        no_opt=no_opt,
        backlog=backlog,
        blocking_threads=blocking_threads,
        respawn_failed_workers=respawn_failed_workers,
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
        ssl_keyfile=ssl_keyfile,
        ssl_certificate=ssl_certificate,
        url_path_prefix=url_path_prefix,
        host=host,
    )


def _run(
    env: LitestarEnv,
    reload: bool,
    port: int,
    wc: int,
    threads: int,
    http: HTTPModes,
    no_opt: bool,
    backlog: int,
    blocking_threads: int,
    respawn_failed_workers: bool,
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
    ssl_keyfile: Path | None,
    ssl_certificate: Path | None,
    url_path_prefix: str | None,
    host: str,
) -> None:
    from dataclasses import asdict

    from granian.constants import Interfaces, Loops
    from granian.log import LogLevels
    from granian.server import Granian
    from litestar.cli._utils import console, show_app_info
    from litestar.cli.commands.core import _server_lifespan
    from litestar.logging.config import LoggingConfig

    if env.app.logging_config is not None and isinstance(env.app.logging_config, LoggingConfig):
        if env.app.logging_config.loggers.get("_granian", None) is None:
            env.app.logging_config.loggers.update(
                {"_granian": {"level": "INFO", "handlers": ["queue_listener"], "propagate": False}},
            )
        env.app.logging_config.configure()
    log_dictconfig = (
        {k: v for k, v in asdict(env.app.logging_config).items() if v is not None}  # type: ignore[call-overload]
        if env.app.logging_config is not None
        else None
    )

    console.rule("[yellow]Starting [blue]Granian[/] server process[/]", align="left")

    show_app_info(env.app)
    with _server_lifespan(env.app):
        Granian(
            env.app_path,
            address=host,
            port=port,
            interface=Interfaces.ASGI,
            workers=wc,
            threads=threads,
            pthreads=blocking_threads,
            threading_mode=threading_mode,
            loop=Loops.uvloop,
            loop_opt=not no_opt,
            log_enabled=True,
            log_level=LogLevels.info,
            log_dictconfig=log_dictconfig,
            http=http,
            websockets=True,
            backlog=backlog,
            respawn_failed_workers=respawn_failed_workers,
            http1_settings=HTTP1Settings(
                keep_alive=http1_keep_alive,
                max_buffer_size=http1_buffer_size,
                pipeline_flush=http1_pipeline_flush,
            ),
            http2_settings=HTTP2Settings(
                adaptive_window=http2_adaptive_window,
                initial_connection_window_size=http2_initial_connection_window_size,
                initial_stream_window_size=http2_initial_stream_window_size,
                keep_alive_interval=http2_keep_alive_interval,
                keep_alive_timeout=http2_keep_alive_timeout,
                max_concurrent_streams=http2_max_concurrent_streams,
                max_frame_size=http2_max_frame_size,
                max_headers_size=http2_max_headers_size,
                max_send_buffer_size=http2_max_send_buffer_size,
            ),
            reload=reload,
            ssl_cert=ssl_certificate,
            ssl_key=ssl_keyfile,
            url_path_prefix=url_path_prefix,
        ).serve()
