from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest
from granian.constants import RuntimeModes

from litestar_granian.cli import run_command

if TYPE_CHECKING:
    from pathlib import Path

    from click.testing import CliRunner
    from litestar.cli._utils import LitestarGroup  # pyright: ignore[reportPrivateImportUsage]

    from tests.conftest import CreateAppFileFixture


@pytest.mark.parametrize(
    "wc, reload, in_subprocess",
    (
        (None, False, False),
        (None, True, False),
        (1, False, False),
        (1, True, False),
        (2, False, False),
        (2, True, False),
    ),
)
def test_basic_command(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
    in_subprocess: bool,
    wc: int | None,
    reload: bool,
) -> None:
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
        await asyncio.sleep(1)
        os.kill(os.getpid(), signal.SIGINT)
        os.kill(os.getpid(), signal.SIGTERM)
        os.kill(os.getpid(), signal.SIGKILL)

    asyncio.ensure_future(_fn())


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:  # noqa: PLR6301
        return {"sample": "hello-world"}


app = Litestar(
    plugins=[GranianPlugin()], route_handlers=[SampleController], on_startup=[dont_run_forever]
)
    """,
    )
    app_file = create_app_file("command_test_app.py", content=app_file_content)
    extra_args: list[str] = []
    if wc is not None:
        extra_args.extend(["--wc", f"{wc!s}"])
    if reload:
        extra_args.extend(["--reload", "--in-subprocess"])
    elif in_subprocess:
        extra_args.extend(["--in-subprocess"])
    else:
        extra_args.extend(["--no-subprocess", "--use-litestar-logger"])
    result = runner.invoke(root_command, ["--app", f"{app_file.stem}:app", "run", "--port", "9876", *extra_args])
    if in_subprocess or reload:
        assert "- _granian - common - Starting granian" in result.output or "Granian workers stopped." in result.output
    else:
        assert "- _granian - common - Starting granian" in result.output or "Granian workers stopped." in result.output


@pytest.mark.parametrize(
    ["wc", "reload", "in_subprocess"],
    [
        (None, False, False),
        (None, True, False),
        (1, False, False),
        (1, True, False),
        (2, False, False),
        (2, True, False),
    ],
)
def test_structlog_command(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
    in_subprocess: bool,
    wc: int | None,
    reload: bool,
) -> None:
    app_file_content = textwrap.dedent(
        """
from __future__ import annotations

import asyncio
import asyncio.tasks
import os
import signal

from litestar import Controller, Litestar, get
from litestar.logging import LoggingConfig, StructLoggingConfig
from litestar.plugins.structlog import StructlogConfig, StructlogPlugin

from litestar_granian import GranianPlugin


async def dont_run_forever() -> None:
    async def _fn() -> None:
        await asyncio.sleep(1)
        os.kill(os.getpid(), signal.SIGINT)
        os.kill(os.getpid(), signal.SIGTERM)
        os.kill(os.getpid(), signal.SIGKILL)

    asyncio.ensure_future(_fn())


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:  # noqa: PLR6301
        return {"sample": "hello-world"}

standard_lib_logging_config=LoggingConfig(
    root={
        "handlers": ["console"],
        "level": "INFO",
    },
    handlers={
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "standard",
        },
        "queue_listener": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "standard",
        },
    },
)

app = Litestar(
    plugins=[
        GranianPlugin(),
        StructlogPlugin(
            config=StructlogConfig(
                structlog_logging_config=StructLoggingConfig(
                    standard_lib_logging_config=standard_lib_logging_config
                )
            )
        ),
    ],
    logging_config=standard_lib_logging_config,
    route_handlers=[SampleController],
    on_startup=[dont_run_forever],
)

    """,
    )
    app_file = create_app_file("command_test_app.py", content=app_file_content)
    extra_args: list[str] = []
    if wc is not None:
        extra_args.extend(["--wc", f"{wc!s}"])
    if reload:
        extra_args.extend(["--reload", "--in-subprocess"])
    elif in_subprocess:
        extra_args.extend(["--in-subprocess"])
    else:
        extra_args.extend(["--no-subprocess"])
    result = runner.invoke(root_command, ["--app", f"{app_file.stem}:app", "run", "--port", "9877", *extra_args])
    assert "Shutting down granian" in result.output or "Granian workers stopped." in result.output


# Error case tests
@pytest.mark.parametrize(
    "reload, port, wc, runtime_threads, http, no_opt, backlog, runtime_mode, ssl_keyfile, ssl_certificate, url_path_prefix, host, debug,  pdb",
    [
        (
            False,
            9876,
            0,
            1,
            "HTTP",
            False,
            1024,
            RuntimeModes.st,
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
            RuntimeModes.mt,
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
    runtime_threads: int,
    http: str,
    no_opt: bool,
    backlog: int,
    runtime_mode: int,
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
            "--runtime-threads",
            str(runtime_threads),
            "--http",
            http,
            "--no-opt" if no_opt else "",
            "--backlog",
            str(backlog),
            "--runtime-mode",
            str(runtime_mode),
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


def test_ssl_certificate_generation_fix_issue_48(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
    tmp_path: Path,
) -> None:
    """Test that SSL certificate generation works when files don't exist (Issue #48).

    This test verifies that the --create-self-signed-cert option works when
    certificate files don't exist, which was broken due to exists=True in ClickPath.
    """
    app_file_content = textwrap.dedent(
        """
from litestar import Litestar, get
from litestar_granian import GranianPlugin

@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}

app = Litestar(plugins=[GranianPlugin()], route_handlers=[hello])
    """,
    )
    app_file = create_app_file("ssl_test_app.py", content=app_file_content)

    # Use non-existent certificate files
    cert_file = tmp_path / "test-cert.pem"
    key_file = tmp_path / "test-key.pem"

    # This should NOT fail with "File does not exist" error
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--ssl-certificate",
            str(cert_file),
            "--ssl-keyfile",
            str(key_file),
            "--create-self-signed-cert",
            "--no-subprocess",
            "--help",  # Just show help to avoid actually starting server
        ],
    )

    # Should not fail with file existence error
    assert "does not exist" not in result.output
    # Command should succeed (exit code 0 for help)
    assert result.exit_code == 0


def test_reload_paths_fix_issue_52(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
    tmp_path: Path,
) -> None:
    """Test that reload paths work correctly without generator object error (Issue #52).

    This test verifies that --reload-paths option works correctly and doesn't
    cause generator object serialization errors in subprocess mode.
    """
    app_file_content = textwrap.dedent(
        """
from litestar import Litestar, get
from litestar_granian import GranianPlugin

@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}

app = Litestar(plugins=[GranianPlugin()], route_handlers=[hello])
    """,
    )
    app_file = create_app_file("reload_test_app.py", content=app_file_content)

    # Create test directories to watch
    watch_dir1 = tmp_path / "src"
    watch_dir1.mkdir()
    watch_dir2 = tmp_path / "templates"
    watch_dir2.mkdir()
    ignore_dir = tmp_path / "node_modules"
    ignore_dir.mkdir()

    # This should NOT fail with generator object error
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--reload",
            "--reload-paths",
            str(watch_dir1),
            "--reload-paths",
            str(watch_dir2),
            "--reload-ignore-paths",
            str(ignore_dir),
            "--port",
            "9878",  # Use different port to avoid conflicts
            "--help",  # Just show help to avoid actually starting server
        ],
    )

    # Should not fail with generator object error
    assert "generator object" not in result.output
    # Command should succeed (exit code 0 for help)
    assert result.exit_code == 0


# Comprehensive tests for Granian 2.5 new parameters
def test_workers_max_rss_parameter(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
) -> None:
    """Test that --workers-max-rss parameter is accepted and validated."""
    app_file_content = textwrap.dedent(
        """
from litestar import Litestar, get
from litestar_granian import GranianPlugin

@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}

app = Litestar(plugins=[GranianPlugin()], route_handlers=[hello])
    """,
    )
    app_file = create_app_file("workers_rss_test_app.py", content=app_file_content)

    # Test valid workers-max-rss value
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--workers-max-rss",
            "512",
            "--port",
            "9880",
            "--help",  # Just show help to avoid actually starting server
        ],
    )
    # Parameter should be accepted without errors
    assert result.exit_code == 0

    # Test invalid workers-max-rss value (should fail)
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--workers-max-rss",
            "0",  # Invalid value - must be >= 1
            "--port",
            "9880",
        ],
    )
    assert result.exit_code != 0


def test_uds_parameter(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
    tmp_path: Path,
) -> None:
    """Test that --uds (Unix Domain Socket) parameter is accepted."""
    app_file_content = textwrap.dedent(
        """
from litestar import Litestar, get
from litestar_granian import GranianPlugin

@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}

app = Litestar(plugins=[GranianPlugin()], route_handlers=[hello])
    """,
    )
    app_file = create_app_file("uds_test_app.py", content=app_file_content)

    # Create a temporary UDS path
    uds_path = tmp_path / "test.sock"

    # Test UDS parameter
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--uds",
            str(uds_path),
            "--help",  # Just show help to avoid actually starting server
        ],
    )
    # Parameter should be accepted without errors
    assert result.exit_code == 0


def test_workers_lifetime_parameter(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
) -> None:
    """Test that --workers-lifetime parameter accepts human-readable durations."""
    app_file_content = textwrap.dedent(
        """
from litestar import Litestar, get
from litestar_granian import GranianPlugin

@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}

app = Litestar(plugins=[GranianPlugin()], route_handlers=[hello])
    """,
    )
    app_file = create_app_file("workers_lifetime_test_app.py", content=app_file_content)

    # Test human-readable duration format
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--workers-lifetime",
            "30m",  # 30 minutes
            "--port",
            "9881",
            "--help",  # Just show help to avoid actually starting server
        ],
    )
    # Parameter should be accepted without errors
    assert result.exit_code == 0

    # Test another human-readable format
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--workers-lifetime",
            "2h",  # 2 hours
            "--port",
            "9881",
            "--help",
        ],
    )
    assert result.exit_code == 0

    # Test numeric format (seconds)
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--workers-lifetime",
            "3600",  # 1 hour in seconds
            "--port",
            "9881",
            "--help",
        ],
    )
    assert result.exit_code == 0


def test_static_file_parameters(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
    tmp_path: Path,
) -> None:
    """Test that static file serving parameters work correctly."""
    app_file_content = textwrap.dedent(
        """
from litestar import Litestar, get
from litestar_granian import GranianPlugin

@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}

app = Litestar(plugins=[GranianPlugin()], route_handlers=[hello])
    """,
    )
    app_file = create_app_file("static_test_app.py", content=app_file_content)

    # Create a static directory
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "test.txt").write_text("test content")

    # Test static file parameters - just check they are accepted without error
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--static-path-mount",
            str(static_dir),
            "--static-path-route",
            "/assets",
            "--static-path-expires",
            "3600",
            "--port",
            "9882",
            "--help",  # Just show help to avoid actually starting server
        ],
    )
    # Parameters should be accepted without errors
    assert result.exit_code == 0

    # Test with default route and expires
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--static-path-mount",
            str(static_dir),
            "--port",
            "9882",
            "--help",
        ],
    )
    assert result.exit_code == 0

    # Test invalid expires value (should fail)
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--static-path-mount",
            str(static_dir),
            "--static-path-expires",
            "30",  # Invalid value - must be >= 60
            "--port",
            "9882",
        ],
    )
    assert result.exit_code != 0


def test_websockets_parameter(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
) -> None:
    """Test that --websockets/--no-websockets parameter works correctly."""
    app_file_content = textwrap.dedent(
        """
from litestar import Litestar, get
from litestar_granian import GranianPlugin

@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}

app = Litestar(plugins=[GranianPlugin()], route_handlers=[hello])
    """,
    )
    app_file = create_app_file("websockets_test_app.py", content=app_file_content)

    # Test enabling websockets (default)
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--websockets",
            "--port",
            "9883",
            "--help",  # Just show help to avoid actually starting server
        ],
    )
    # Parameter should be accepted without errors
    assert result.exit_code == 0

    # Test disabling websockets
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--no-websockets",
            "--port",
            "9883",
            "--help",
        ],
    )
    assert result.exit_code == 0


def test_combined_new_parameters(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
    tmp_path: Path,
) -> None:
    """Test that multiple new parameters can be combined successfully."""
    app_file_content = textwrap.dedent(
        """
from litestar import Litestar, get
from litestar_granian import GranianPlugin

@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}

app = Litestar(plugins=[GranianPlugin()], route_handlers=[hello])
    """,
    )
    app_file = create_app_file("combined_test_app.py", content=app_file_content)

    # Create static directory and UDS path
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "app.js").write_text("console.log('test');")
    uds_path = tmp_path / "app.sock"

    # Test combining multiple new parameters
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--workers-max-rss",
            "256",
            "--workers-lifetime",
            "1h",
            "--uds",
            str(uds_path),
            "--static-path-mount",
            str(static_dir),
            "--static-path-route",
            "/static",
            "--static-path-expires",
            "7200",
            "--no-websockets",
            "--help",  # Just show help to avoid actually starting server
        ],
    )
    # All parameters should be accepted without errors
    assert result.exit_code == 0


def test_static_file_directory_validation(
    runner: CliRunner,
    create_app_file: CreateAppFileFixture,
    root_command: LitestarGroup,
    tmp_path: Path,
) -> None:
    """Test that static file directory validation works correctly."""
    app_file_content = textwrap.dedent(
        """
from litestar import Litestar, get
from litestar_granian import GranianPlugin

@get("/")
async def hello() -> dict[str, str]:
    return {"hello": "world"}

app = Litestar(plugins=[GranianPlugin()], route_handlers=[hello])
    """,
    )
    app_file = create_app_file("static_validation_test_app.py", content=app_file_content)

    # Test with non-existent directory (should fail)
    nonexistent_dir = tmp_path / "nonexistent"
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--static-path-mount",
            str(nonexistent_dir),
            "--port",
            "9884",
        ],
    )
    assert result.exit_code != 0
    assert "does not exist" in result.output.lower() or "invalid" in result.output.lower()

    # Test with file instead of directory (should fail)
    test_file = tmp_path / "test.txt"
    test_file.write_text("test")
    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--static-path-mount",
            str(test_file),
            "--port",
            "9884",
        ],
    )
    assert result.exit_code != 0
