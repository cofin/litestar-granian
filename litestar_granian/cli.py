from __future__ import annotations

import multiprocessing
import os
from typing import TYPE_CHECKING

import click
from click import Context, command, option
from granian.constants import HTTPModes, Interfaces, Loops, ThreadModes
from granian.server import Granian
from litestar.cli._utils import LitestarEnv, console, show_app_info

if TYPE_CHECKING:
    from pathlib import Path


@command(name="run")
@option("-r", "--reload", help="Reload server on changes", default=False, is_flag=True)
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
@option("--url-path-prefix", help="URL path prefix the app is mounted on", default=None, show_default=False)
@option("-d", "--debug", help="Run app in debug mode", is_flag=True)
@option("-P", "--pdb", "--use-pdb", help="Drop into PDB on an exception", is_flag=True)
def run_command(
    reload: bool,
    port: int,
    wc: int,
    threads: int,
    http: HTTPModes,
    no_opt: bool,
    backlog: int,
    threading_mode: ThreadModes,
    ssl_keyfile: Path | None,
    ssl_certificate: Path | None,
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

    if debug:
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
    app = env.app

    threading_mode = threading_mode or ThreadModes.workers
    host = env.host or host
    port = env.port if env.port is not None else port
    reload = env.reload or reload
    workers = env.web_concurrency or wc

    console.rule("[yellow]Starting [blue]granian[/] server process[/]", align="left")

    show_app_info(app)
    Granian(
        env.app_path,
        address=host,
        port=port,
        interface=Interfaces.ASGI,
        workers=workers,
        threads=threads,
        pthreads=threads,
        threading_mode=threading_mode,
        loop=Loops.uvloop,
        loop_opt=not no_opt,
        http=http,
        websockets=True,
        backlog=backlog,
        reload=reload,
        ssl_cert=ssl_certificate,
        ssl_key=ssl_keyfile,
        url_path_prefix=url_path_prefix,
    ).serve()
