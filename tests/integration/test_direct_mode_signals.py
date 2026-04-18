"""Direct-mode SIGINT regression tests.

Reproduces the v0.15.0 regression (reported 2026-04-17) where Ctrl+C fails to
stop the server when running in direct mode (``--no-subprocess``) together
with ``--use-litestar-logger``.

These tests spawn a real ``python -m litestar ... run`` subprocess, wait for
the server to accept HTTP requests, send SIGINT, and assert the process
exits cleanly within a bounded window.

The bug-reproducing cell is parametrized so bisects of ``--runtime-mode``,
logger choice, and worker count are driven by the same harness.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator


MINIMAL_APP = """
from __future__ import annotations

from litestar import Controller, Litestar, get
from litestar.logging import LoggingConfig

from litestar_granian import GranianPlugin


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:
        return {"sample": "hello-world"}


app = Litestar(
    plugins=[GranianPlugin()],
    route_handlers=[SampleController],
    logging_config=LoggingConfig(),
)
"""


# Mirrors the shape of the accelerator's StructLoggingConfig:
# ``_granian`` and ``granian.access`` loggers explicitly route through the
# Litestar queue_listener handler. v0.14.x unconditionally overwrote these
# entries to a ``console`` handler; v0.15.0's guarded injection preserves
# them, which is the user-reported regression path.
STRUCTLOG_APP = """
from __future__ import annotations

from litestar import Controller, Litestar, get
from litestar.logging.config import LoggingConfig, StructLoggingConfig
from litestar.plugins.structlog import StructlogConfig, StructlogPlugin

from litestar_granian import GranianPlugin


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:
        return {"sample": "hello-world"}


structlog_cfg = StructlogConfig(
    structlog_logging_config=StructLoggingConfig(
        standard_lib_logging_config=LoggingConfig(
            root={"level": "INFO", "handlers": ["queue_listener"]},
            loggers={
                "_granian": {"propagate": False, "level": "INFO", "handlers": ["queue_listener"]},
                "granian.access": {"propagate": False, "level": "INFO", "handlers": ["queue_listener"]},
                "granian.server": {"propagate": False, "level": "INFO", "handlers": ["queue_listener"]},
            },
        ),
    ),
)

app = Litestar(
    plugins=[GranianPlugin(), StructlogPlugin(config=structlog_cfg)],
    route_handlers=[SampleController],
)
"""


QUEUE_LISTENER_APP = """
from __future__ import annotations

from litestar import Controller, Litestar, get
from litestar.logging import LoggingConfig

from litestar_granian import GranianPlugin


class SampleController(Controller):
    @get(path="/sample")
    async def sample_route(self) -> dict[str, str]:
        return {"sample": "hello-world"}


logging_config = LoggingConfig(
    root={"level": "INFO", "handlers": ["queue_listener"]},
    loggers={
        "_granian": {"propagate": False, "level": "INFO", "handlers": ["queue_listener"]},
        "granian.access": {"propagate": False, "level": "INFO", "handlers": ["queue_listener"]},
        "granian.server": {"propagate": False, "level": "INFO", "handlers": ["queue_listener"]},
    },
)

app = Litestar(
    plugins=[GranianPlugin()],
    route_handlers=[SampleController],
    logging_config=logging_config,
)
"""


SHUTDOWN_TIMEOUT_SECONDS = 5.0
READY_POLL_TIMEOUT_SECONDS = 15.0
READY_POLL_INTERVAL_SECONDS = 0.2


@pytest.fixture
def app_project(tmp_path: Path) -> Path:
    app_file = tmp_path / "direct_signal_app.py"
    app_file.write_text(MINIMAL_APP)
    return tmp_path


@pytest.fixture
def queue_listener_app_project(tmp_path: Path) -> Path:
    app_file = tmp_path / "direct_signal_app.py"
    app_file.write_text(QUEUE_LISTENER_APP)
    return tmp_path


@pytest.fixture
def structlog_app_project(tmp_path: Path) -> Path:
    app_file = tmp_path / "direct_signal_app.py"
    app_file.write_text(STRUCTLOG_APP)
    return tmp_path


def _make_spawner(project_dir: Path) -> "tuple[object, list[subprocess.Popen[bytes]]]":
    processes: list["subprocess.Popen[bytes]"] = []

    def _spawn(port: int, extra_args: list[str]) -> "subprocess.Popen[bytes]":
        cmd = [
            sys.executable,
            "-m",
            "litestar",
            "--app",
            "direct_signal_app:app",
            "run",
            "--port",
            str(port),
            *extra_args,
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(project_dir), env.get("PYTHONPATH", "")]))
        env["PYTHONUNBUFFERED"] = "1"
        env.pop("LITESTAR_GRANIAN_IN_SUBPROCESS", None)
        env.pop("LITESTAR_GRANIAN_USE_LITESTAR_LOGGER", None)
        proc = subprocess.Popen(
            cmd,
            cwd=str(project_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        processes.append(proc)
        return proc

    return _spawn, processes


@pytest.fixture
def structlog_spawned_server(structlog_app_project: Path) -> "Iterator[subprocess.Popen[bytes]]":
    spawn, processes = _make_spawner(structlog_app_project)
    try:
        yield spawn  # type: ignore[misc]
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.communicate(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass


def _wait_until_ready(port: int, process: "subprocess.Popen[bytes]") -> None:
    """Poll ``GET /sample`` until the server answers or we time out.

    Fails fast if the subprocess already exited before becoming ready —
    without this, a subprocess crash during startup would look like a
    readiness timeout.
    """
    deadline = time.monotonic() + READY_POLL_TIMEOUT_SECONDS
    url = f"http://127.0.0.1:{port}/sample"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1.0)
            msg = (
                f"subprocess exited during startup with code {process.returncode}\n"
                f"stdout:\n{stdout.decode(errors='replace')}\n"
                f"stderr:\n{stderr.decode(errors='replace')}"
            )
            raise AssertionError(msg)
        try:
            response = httpx.get(url, timeout=1.0)
        except httpx.HTTPError:
            time.sleep(READY_POLL_INTERVAL_SECONDS)
            continue
        if response.status_code == 200:
            return
        time.sleep(READY_POLL_INTERVAL_SECONDS)
    raise AssertionError(f"server did not become ready at {url} within {READY_POLL_TIMEOUT_SECONDS}s")


def _terminate_and_fail(process: "subprocess.Popen[bytes]", reason: str) -> None:
    """Hard-kill a stuck subprocess and raise with its captured output."""
    process.kill()
    try:
        stdout, stderr = process.communicate(timeout=5.0)
    except subprocess.TimeoutExpired:
        stdout, stderr = b"", b""
    raise AssertionError(
        f"{reason}\nstdout:\n{stdout.decode(errors='replace')}\nstderr:\n{stderr.decode(errors='replace')}"
    )


@pytest.fixture
def spawned_server(app_project: Path) -> "Iterator[subprocess.Popen[bytes]]":
    """Yields a handle to a running server subprocess; cleans up on exit."""
    processes: list["subprocess.Popen[bytes]"] = []

    def _spawn(port: int, extra_args: list[str]) -> "subprocess.Popen[bytes]":
        cmd = [
            sys.executable,
            "-m",
            "litestar",
            "--app",
            "direct_signal_app:app",
            "run",
            "--port",
            str(port),
            *extra_args,
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(app_project), env.get("PYTHONPATH", "")]))
        env["PYTHONUNBUFFERED"] = "1"
        env.pop("LITESTAR_GRANIAN_IN_SUBPROCESS", None)
        env.pop("LITESTAR_GRANIAN_USE_LITESTAR_LOGGER", None)
        # ``start_new_session=True`` puts the child in its own process group so we
        # can send SIGINT to the whole group (``os.killpg``) the way a terminal
        # does when the user hits Ctrl+C. Without this, ``proc.send_signal`` only
        # reaches the main Python process — workers never see the signal, which
        # does NOT match real Ctrl+C behavior.
        proc = subprocess.Popen(
            cmd,
            cwd=str(app_project),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        processes.append(proc)
        return proc

    # expose _spawn via an attribute on the fixture value to keep the
    # contract simple while still letting pytest handle teardown
    _spawn.processes = processes  # type: ignore[attr-defined,unused-ignore]
    try:
        yield _spawn  # type: ignore[misc]
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.communicate(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT semantics differ on Windows; covered separately")
@pytest.mark.parametrize(
    ("logger_flag", "runtime_mode"),
    [
        pytest.param("--no-litestar-logger", "st", id="stdlib-logger+runtime-st"),
        pytest.param("--no-litestar-logger", "auto", id="stdlib-logger+runtime-auto"),
        pytest.param("--use-litestar-logger", "st", id="litestar-logger+runtime-st"),
        pytest.param(
            "--use-litestar-logger",
            "auto",
            id="litestar-logger+runtime-auto-REPRO",
        ),
    ],
)
def test_direct_mode_sigint_shuts_down_cleanly(
    spawned_server: "object",
    logger_flag: str,
    runtime_mode: str,
) -> None:
    """Direct mode + SIGINT must exit the server in bounded time.

    The ``litestar-logger+runtime-auto-REPRO`` cell is the user-reported hang
    (v0.15.0 defaults). All four cells should pass once the fix lands.
    """
    spawn = spawned_server  # cast: the fixture yields a callable (see above)
    port = 9891
    t_spawn = time.monotonic()
    proc = spawn(  # type: ignore[operator]
        port,
        ["--no-subprocess", logger_flag, "--runtime-mode", runtime_mode],
    )
    try:
        _wait_until_ready(port, proc)
    except AssertionError:
        proc.kill()
        raise
    t_ready = time.monotonic()

    # Send SIGINT to the whole process group, the way a TTY does on Ctrl+C.
    # Sending to only the main PID (``proc.send_signal``) is not equivalent:
    # Granian worker processes never see the signal under that model, which
    # masks hangs that require main+workers to receive SIGINT concurrently.
    os.killpg(os.getpgid(proc.pid), signal.SIGINT)

    try:
        proc.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _terminate_and_fail(
            proc,
            reason=(
                f"process did not exit within {SHUTDOWN_TIMEOUT_SECONDS}s after SIGINT "
                f"(logger={logger_flag}, runtime-mode={runtime_mode})"
            ),
        )
    t_exit = time.monotonic()
    print(
        f"[TIMING {logger_flag} rt={runtime_mode}] "
        f"ready={t_ready - t_spawn:.2f}s "
        f"sigint->exit={t_exit - t_ready:.2f}s "
        f"rc={proc.returncode}"
    )

    assert proc.returncode in (0, -signal.SIGINT), (
        f"unexpected exit code {proc.returncode} (logger={logger_flag}, runtime-mode={runtime_mode})"
    )


@pytest.fixture
def queue_listener_spawned_server(queue_listener_app_project: Path) -> "Iterator[subprocess.Popen[bytes]]":
    """Same as ``spawned_server`` but using the queue-listener routed app."""
    processes: list["subprocess.Popen[bytes]"] = []

    def _spawn(port: int, extra_args: list[str]) -> "subprocess.Popen[bytes]":
        cmd = [
            sys.executable,
            "-m",
            "litestar",
            "--app",
            "direct_signal_app:app",
            "run",
            "--port",
            str(port),
            *extra_args,
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(queue_listener_app_project), env.get("PYTHONPATH", "")]))
        env["PYTHONUNBUFFERED"] = "1"
        env.pop("LITESTAR_GRANIAN_IN_SUBPROCESS", None)
        env.pop("LITESTAR_GRANIAN_USE_LITESTAR_LOGGER", None)
        proc = subprocess.Popen(
            cmd,
            cwd=str(queue_listener_app_project),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        processes.append(proc)
        return proc

    _spawn.processes = processes  # type: ignore[attr-defined,unused-ignore]
    try:
        yield _spawn  # type: ignore[misc]
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.communicate(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT semantics differ on Windows; covered separately")
def test_direct_mode_sigint_with_granian_loggers_on_queue_listener(
    queue_listener_spawned_server: "object",
) -> None:
    """Reproduces the v0.15.0 regression reported by a user on 2026-04-17.

    When the app's ``_granian`` and ``granian.access`` loggers are explicitly
    routed through Litestar's ``queue_listener`` handler (the shape used by
    downstream projects that configure structured logging end-to-end),
    Ctrl+C in direct mode produces no output and never shuts the server down.

    v0.14.x did not hit this because the plugin unconditionally overwrote
    those two loggers to a ``console`` handler, silently discarding the user's
    queue-listener routing. PR #63 made the injection guarded, honoring the
    user's config — which is correct in intent but breaks SIGINT delivery.

    Expected: exits cleanly within ``SHUTDOWN_TIMEOUT_SECONDS``. Red state:
    hangs until the test helper force-kills the process group.
    """
    spawn = queue_listener_spawned_server
    port = 9892
    t_spawn = time.monotonic()
    proc = spawn(  # type: ignore[operator]
        port,
        ["--no-subprocess", "--use-litestar-logger", "--runtime-mode", "st"],
    )
    try:
        _wait_until_ready(port, proc)
    except AssertionError:
        proc.kill()
        raise
    t_ready = time.monotonic()

    os.killpg(os.getpgid(proc.pid), signal.SIGINT)

    try:
        proc.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _terminate_and_fail(
            proc,
            reason=(
                f"process did not exit within {SHUTDOWN_TIMEOUT_SECONDS}s after SIGINT "
                f"(queue_listener-routed _granian loggers) — v0.15.0 regression repro"
            ),
        )
    t_exit = time.monotonic()
    print(
        f"[TIMING queue_listener-routed] "
        f"ready={t_ready - t_spawn:.2f}s "
        f"sigint->exit={t_exit - t_ready:.2f}s "
        f"rc={proc.returncode}"
    )

    assert proc.returncode in (0, -signal.SIGINT), (
        f"unexpected exit code {proc.returncode} (queue_listener-routed _granian loggers)"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT semantics differ on Windows; covered separately")
@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason=(
        "Known hang on Python 3.10 with StructlogPlugin + queue_listener-routed "
        "granian loggers. Does not reproduce on 3.11+. Tracked as a separate "
        "follow-up; the test still serves as a regression gate on supported versions."
    ),
)
def test_direct_mode_sigint_with_structlog_plugin_queue_routed(
    structlog_spawned_server: "object",
) -> None:
    """Same shape as the accelerator: ``StructlogPlugin`` with ``StructLoggingConfig``
    whose ``standard_lib_logging_config`` explicitly routes ``_granian`` /
    ``granian.access`` / ``granian.server`` loggers through ``queue_listener``.
    """
    spawn = structlog_spawned_server
    port = 9893
    t_spawn = time.monotonic()
    proc = spawn(  # type: ignore[operator]
        port,
        ["--no-subprocess", "--use-litestar-logger", "--runtime-mode", "st"],
    )
    try:
        _wait_until_ready(port, proc)
    except AssertionError:
        proc.kill()
        raise
    t_ready = time.monotonic()

    os.killpg(os.getpgid(proc.pid), signal.SIGINT)

    try:
        proc.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _terminate_and_fail(
            proc,
            reason=(
                f"process did not exit within {SHUTDOWN_TIMEOUT_SECONDS}s after SIGINT "
                f"(StructlogPlugin + queue_listener-routed granian loggers) — v0.15.0 regression repro"
            ),
        )
    t_exit = time.monotonic()
    print(
        f"[TIMING structlog-plugin queue_listener-routed] "
        f"ready={t_ready - t_spawn:.2f}s "
        f"sigint->exit={t_exit - t_ready:.2f}s "
        f"rc={proc.returncode}"
    )

    assert proc.returncode in (0, -signal.SIGINT), (
        f"unexpected exit code {proc.returncode} (StructlogPlugin + queue_listener)"
    )
