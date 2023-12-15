from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import TYPE_CHECKING

import click
from click import Context, command, option
from granian.constants import HTTPModes, ThreadModes

if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.cli._utils import LitestarEnv


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
@option(
    "--create-self-signed-cert",
    help="If certificate and key are not found at specified locations, create a self-signed certificate and a key",
    is_flag=True,
)
@option("--url-path-prefix", help="URL path prefix the app is mounted on", default=None, show_default=False)
@option("-d", "--debug", help="Run app in debug mode", is_flag=True)
@option("-P", "--pdb", "--use-pdb", help="Drop into PDB on an exception", is_flag=True)
def run_command(
    app: Litestar,
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
    from litestar.cli._utils import (
        create_ssl_files,
    )

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

    if env.app.logging_config is not None:
        if env.app.logging_config.loggers.get("_granian", None) is None:  # type: ignore[attr-defined]
            env.app.logging_config.loggers.update(  # type: ignore[attr-defined]
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
            pthreads=threads,
            threading_mode=threading_mode,
            loop=Loops.uvloop,
            loop_opt=not no_opt,
            log_enabled=True,
            log_level=LogLevels.info,
            log_dictconfig=log_dictconfig,
            http=http,
            websockets=True,
            backlog=backlog,
            reload=reload,
            ssl_cert=ssl_certificate,
            ssl_key=ssl_keyfile,
            url_path_prefix=url_path_prefix,
        ).serve()
