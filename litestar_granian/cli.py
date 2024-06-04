from __future__ import annotations

import multiprocessing
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
from click import Context, command, option
from granian import Granian
from granian.constants import HTTPModes, Interfaces, Loops, ThreadModes
from granian.errors import ConfigurationError
from granian.http import HTTP1Settings, HTTP2Settings
from litestar.cli._utils import LitestarEnv

try:
    from litestar.cli._utils import isatty  # type: ignore[attr-defined,unused-ignore]
except ImportError:  # pragma: nocover

    def isatty() -> bool:  # pragma: nocover
        """Detect if a terminal is TTY enabled.

        This was added in Litestar 2.8 and is backported for compatibility.

        This is a convenience wrapper around the built in system methods.  This allows for easier testing of TTY/non-TTY modes.
        """
        return sys.stdout.isatty()


if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.cli._utils import LitestarEnv


@command(name="run", context_settings={"show_default": True}, help="Start application server")
@option("-p", "--port", help="Serve under this port", type=int, default=8000, show_default=True, envvar="LITESTAR_PORT")
@option(
    "-W",
    "--wc",
    "--web-concurrency",
    "--workers",
    help="The number of processes to start.",
    type=click.IntRange(min=1, max=multiprocessing.cpu_count() + 1),
    show_default=True,
    default=1,
    envvar=["LITESTAR_WEB_CONCURRENCY", "WEB_CONCURRENCY"],
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
@option("--threading-mode", help="Threading mode to use.", type=ThreadModes, default=ThreadModes.workers.value)
@option("--http", help="HTTP Version to use (HTTP or HTTP2)", type=HTTPModes, default=HTTPModes.auto.value)
@option("--opt", help="Enable additional event loop optimizations", is_flag=True, default=False)
@option(
    "--backlog",
    help="Maximum number of connections to hold in backlog.",
    type=click.IntRange(min=128),
    show_default=True,
    default=1024,
)
@option("-H", "--host", help="Server under this host", default="127.0.0.1", show_default=True, envvar="LITESTAR_HOST")
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
    envvar="LITESTAR_CREATE_SELF_SIGNED_CERT",
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
@option("--url-path-prefix", help="URL path prefix the app is mounted on", default=None, show_default=False)
@option("-d", "--debug", help="Run app in debug mode", is_flag=True, envvar="LITESTAR_DEBUG")
@option("-P", "--pdb", "--use-pdb", help="Drop into PDB on an exception", is_flag=True, envvar="LITESTAR_PDB")
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
@option("-r", "--reload/--no-reload", help="Reload server on changes", default=False, is_flag=True)
@option(
    "--process-name",
    help="Set a custom name for processes.",
)
def run_command(
    app: Litestar,
    reload: bool,
    port: int,
    wc: int,
    threads: int,
    blocking_threads: int,
    respawn_failed_workers: bool,
    respawn_interval: float,
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
    opt: bool,
    backlog: int,
    threading_mode: ThreadModes,
    ssl_keyfile: Path | None,
    ssl_certificate: Path | None,
    create_self_signed_cert: bool,
    url_path_prefix: str | None,
    host: str,
    process_name: str | None,
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

    from granian._loops import loops
    from granian.constants import ThreadModes
    from litestar.cli._utils import console, create_ssl_files, show_app_info
    from litestar.cli.commands.core import _server_lifespan  # pyright: ignore[reportPrivateUsage]

    loops.get("auto")
    if debug:
        app.debug = True
        os.environ["LITESTAR_DEBUG"] = "1"
    if pdb:
        os.environ["LITESTAR_PDB"] = "1"
    quiet_console = os.getenv("LITESTAR_QUIET_CONSOLE") or False
    if callable(ctx.obj):
        ctx.obj = ctx.obj()
    else:
        if debug:
            ctx.obj.app.debug = True
        if pdb:
            ctx.obj.app.pdb_on_exception = True

    env: LitestarEnv = ctx.obj
    if env.is_app_factory:
        console.print(
            r"granian does not support the app factory pattern.",
        )
        sys.exit(1)
    threading_mode = threading_mode or ThreadModes.workers
    workers = wc
    if create_self_signed_cert:
        _cert, _key = create_ssl_files(str(ssl_certificate), str(ssl_keyfile), host)
        ssl_certificate = ssl_certificate or Path(_cert) if _cert is not None else None
        ssl_keyfile = ssl_keyfile or Path(_key) if _key is not None else None

    if not quiet_console and isatty():
        console.rule("[yellow]Starting [blue]Granian[/] server process[/]", align="left")
        show_app_info(env.app)
    with _server_lifespan(env.app):
        _run_granian(
            env=env,
            reload=reload,
            port=port,
            wc=workers,
            threads=threads,
            http=http,
            opt=opt,
            backlog=backlog,
            blocking_threads=blocking_threads,
            respawn_failed_workers=respawn_failed_workers,
            respawn_interval=respawn_interval,
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
            ssl_keyfile=ssl_keyfile,
            ssl_certificate=ssl_certificate,
            url_path_prefix=url_path_prefix,
            host=host,
        )


def _convert_granian_args(args: dict[str, Any]) -> list[str]:
    process_args = []
    for arg, value in args.items():
        if isinstance(value, bool):
            if value:
                process_args.append(f"--{arg}")
            else:
                process_args.append(f"--no-{arg}")
        elif isinstance(value, tuple):
            process_args.extend(f"--{arg}={item}" for item in value)
        else:
            process_args.append(f"--{arg}={value}")

    return process_args


def _run_granian(
    env: LitestarEnv,
    host: str,
    port: int,
    reload: bool,
    wc: int,
    threads: int,
    http: HTTPModes,
    opt: bool,
    backlog: int,
    blocking_threads: int,
    respawn_failed_workers: bool,
    respawn_interval: float,
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
    process_name: str | None,
    ssl_keyfile: Path | None,
    ssl_certificate: Path | None,
    url_path_prefix: str | None,
) -> None:
    server = Granian(
        env.app_path,
        address=host,
        port=port,
        interface=Interfaces.ASGI,
        workers=wc,
        threads=threads,
        blocking_threads=blocking_threads,
        threading_mode=threading_mode,
        loop=Loops.auto,
        loop_opt=opt,
        http=http,
        websockets=http.value != HTTPModes.http2.value,
        backlog=backlog,
        backpressure=None,
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
        ssl_cert=ssl_certificate,
        ssl_key=ssl_keyfile,
        url_path_prefix=url_path_prefix,
        respawn_failed_workers=respawn_failed_workers,
        respawn_interval=respawn_interval,
        reload=reload,
        process_name=process_name,
    )

    try:
        server.serve()
    except ConfigurationError:
        raise click.exceptions.Exit(1)  # noqa: B904


def _run_granian_in_subprocess(
    *,
    env: LitestarEnv,
    host: str,
    port: int,
    reload: bool,
    wc: int,
    threads: int,
    http: HTTPModes,
    opt: bool,
    backlog: int,
    blocking_threads: int,
    respawn_failed_workers: bool,
    respawn_interval: float,
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
    process_name: str | None,
    ssl_keyfile: Path | None,
    ssl_certificate: Path | None,
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
        "opt": opt,
        "respawn-failed-workers": respawn_failed_workers,
        "respawn-interval": respawn_interval,
        "backlog": backlog,
    }
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
        process_args["ssl-certfile"] = ssl_certificate
    if ssl_keyfile is not None:
        process_args["ssl-keyfile"] = ssl_keyfile
    if process_name is not None:
        process_args["process-name"] = process_name
    subprocess.run(
        [sys.executable, "-m", "granian", env.app_path, *_convert_granian_args(process_args)],  # noqa: S603
        check=True,
    )
