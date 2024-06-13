from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest
from granian.constants import ThreadModes

from litestar_granian.cli import run_command

if TYPE_CHECKING:
    from click.testing import CliRunner
    from litestar.cli._utils import LitestarGroup

    from tests.conftest import CreateAppFileFixture


def test_basic_command(runner: CliRunner, create_app_file: CreateAppFileFixture, root_command: LitestarGroup) -> None:
    app_file_content = textwrap.dedent(
        """
from __future__ import annotations

import asyncio
import asyncio.tasks
import os
import signal

from litestar import Controller, Litestar, get

from litestar_granian import GranianPlugin

async def dont_run_forever() -> None:
    async def _fn() -> None:
        await asyncio.sleep(10)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.ensure_future(_fn())

class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:  # noqa: PLR6301
        return {"sample": "hello-world"}


app = Litestar(plugins=[GranianPlugin()], route_handlers=[SampleController], on_startup=[dont_run_forever])
    """,
    )
    app_file = create_app_file("command_test_app.py", content=app_file_content)
    result = runner.invoke(root_command, ["--app", f"{app_file.stem}:app", "run"])

    assert "_granian.asgi.serve - serve - Started worker-1" in result.output


def test_structlog_command(
    runner: CliRunner, create_app_file: CreateAppFileFixture, root_command: LitestarGroup
) -> None:
    app_file_content = textwrap.dedent(
        """
from __future__ import annotations

import asyncio
import asyncio.tasks
import os
import signal

from litestar import Controller, Litestar, get
from litestar.plugins.structlog import StructlogPlugin

from litestar_granian import GranianPlugin


async def dont_run_forever() -> None:
    async def _fn() -> None:
        await asyncio.sleep(3)
        os.kill(os.getpid(), signal.SIGTERM)

    asyncio.ensure_future(_fn())

class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:  # noqa: PLR6301 
        return {"sample": "hello-world"}


app = Litestar(
    plugins=[GranianPlugin(), StructlogPlugin()], route_handlers=[SampleController], on_startup=[dont_run_forever]
)

    """,
    )
    app_file = create_app_file("command_test_app.py", content=app_file_content)
    result = runner.invoke(root_command, ["--app", f"{app_file.stem}:app", "run"])

    assert "_granian.asgi.serve - serve - Started worker-1" in result.output


# Error case tests
@pytest.mark.parametrize(
    "reload, port, wc, threads, http, no_opt, backlog, threading_mode, ssl_keyfile, ssl_certificate, url_path_prefix, host, debug,  pdb",
    [
        (
            False,
            8000,
            0,
            1,
            "HTTP",
            False,
            1024,
            ThreadModes.workers,
            None,
            None,
            None,
            "127.0.0.1",
            False,
            False,
        ),  # Invalid wc value
        (
            True,
            8080,
            2,
            0,
            "HTTP2",
            True,
            2048,
            "threads",
            "keyfile.pem",
            "certificate.pem",
            "/prefix",
            "localhost",
            True,
            True,
        ),  # Invalid threads value
    ],
)
def test_run_command_error_cases(
    runner: CliRunner,
    reload: bool,
    port: int,
    wc: int,
    threads: int,
    http: str,
    no_opt: bool,
    backlog: int,
    threading_mode: str,
    ssl_keyfile: str,
    ssl_certificate: str,
    url_path_prefix: str,
    host: str,
    debug: bool,
    pdb: bool,
) -> None:
    result = runner.invoke(
        run_command,
        [
            "--reload" if reload else "",
            "--port",
            str(port),
            "--wc",
            str(wc),
            "--threads",
            str(threads),
            "--http",
            http,
            "--no-opt" if no_opt else "",
            "--backlog",
            str(backlog),
            "--threading-mode",
            threading_mode,
            "--ssl-keyfile",
            ssl_keyfile,
            "--ssl-certificate",
            ssl_certificate,
            "--url-path-prefix",
            url_path_prefix,
            "--host",
            host,
            "--debug" if debug else "",
            "--pdb" if pdb else "",
        ],
    )
    assert result.exit_code != 0
    # Add assertions for the expected behavior
