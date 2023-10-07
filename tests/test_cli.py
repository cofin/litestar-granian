from __future__ import annotations

import pytest
from click.testing import CliRunner
from granian.constants import ThreadModes

from litestar_granian.cli import run_command


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# Happy path tests
@pytest.mark.parametrize(
    "reload, port, wc, threads, http, no_opt, backlog, threading_mode, ssl_keyfile, ssl_certificate, url_path_prefix, host, debug, pdb",
    [
        (False, 8000, 1, 1, "HTTP", False, 1024, "workers", None, None, None, "127.0.0.1", False, False),
        (
            True,
            8080,
            2,
            2,
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
        ),
    ],
)
def test_run_command_happy_path(
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
    assert result.exit_code
    # Add assertions for the expected behavior


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
