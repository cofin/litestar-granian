from __future__ import annotations

import json
import os
import signal
import sys
import sysconfig
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.request import urlopen

import pytest
from packaging.version import Version
from websockets.sync.client import connect

from tests.integration._runtime import (
    descendants,
    finish_process,
    free_port,
    start_process,
    terminate_process_group,
    wait_for_descendants_to_exit,
    wait_for_port,
)

if TYPE_CHECKING:
    from tests.conftest import CreateAppFileFixture

_APP = """
from __future__ import annotations

from litestar import Litestar, WebSocket, get, websocket

from litestar_granian import GranianPlugin


@get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@websocket("/ws")
async def echo(socket: WebSocket) -> None:
    await socket.accept()
    await socket.send_text(await socket.receive_text())
    await socket.close()


app = Litestar(route_handlers=[health, echo], plugins=[GranianPlugin()])
"""

_LOOP = os.environ.get("LITESTAR_GRANIAN_TEST_LOOP", "asyncio")
_LOOP_MODULES = {
    "asyncio": None,
    "rloop": "rloop",
    "uvloop": "uvloop",
    "winloop": "winloop",
}
_CAPABILITY_SKIPS = {
    "rloop": {
        "tls": "rloop 0.3.1 does not implement the TLS APIs required by this cell",
        "unix-domain-sockets": "rloop 0.3.1 does not implement Unix-domain socket servers",
        "debug": "rloop 0.3.1 does not implement asyncio debug mode",
        "low-level-apis": "rloop 0.3.1 does not implement the low-level asyncio APIs required by this cell",
    }
}
_FREE_THREADED = sysconfig.get_config_var("Py_GIL_DISABLED") == 1


def _uvloop_is_quarantined(*, loop: str, free_threaded: bool, loop_version: str) -> bool:
    return loop == "uvloop" and free_threaded and Version(loop_version) <= Version("0.22.1")


def _selected_loop_version() -> str:
    try:
        return version(_LOOP)
    except PackageNotFoundError:
        return "0"


def _skip_ineligible_loop() -> None:
    if _LOOP not in _LOOP_MODULES:
        pytest.fail(f"unsupported LITESTAR_GRANIAN_TEST_LOOP value: {_LOOP!r}")
    if _LOOP == "winloop" and sys.platform != "win32":
        pytest.skip("winloop 0.6.3 is exercised only by the isolated Windows matrix")
    if _LOOP in {"rloop", "uvloop"} and sys.platform == "win32":
        pytest.skip(f"{_LOOP} is exercised only by the isolated Linux/macOS matrix")
    module = _LOOP_MODULES[_LOOP]
    if module is not None and find_spec(module) is None:
        pytest.skip(f"{_LOOP} must be installed by its isolated loop matrix cell")
    if _uvloop_is_quarantined(
        loop=_LOOP,
        free_threaded=_FREE_THREADED,
        loop_version=_selected_loop_version(),
    ):
        pytest.skip("uvloop <=0.22.1 on free-threaded Python is quarantined: uvloop#720 / PR #721")


def _require_capability(capability: str) -> None:
    if reason := _CAPABILITY_SKIPS.get(_LOOP, {}).get(capability):
        pytest.skip(reason)


@pytest.mark.parametrize(
    ("loop", "free_threaded", "loop_version", "expected"),
    [
        pytest.param("uvloop", True, "0.22.0", True, id="affected-release"),
        pytest.param("uvloop", True, "0.22.1", True, id="affected-boundary"),
        pytest.param("uvloop", True, "0.22.2", False, id="fixed-release"),
        pytest.param("uvloop", False, "0.22.1", False, id="gil-build"),
        pytest.param("asyncio", True, "0.22.1", False, id="stdlib-loop"),
    ],
)
def test_uvloop_free_threaded_quarantine_is_deterministic(
    loop: str,
    free_threaded: bool,
    loop_version: str,
    expected: bool,
) -> None:
    assert (
        _uvloop_is_quarantined(
            loop=loop,
            free_threaded=free_threaded,
            loop_version=loop_version,
        )
        is expected
    )


def test_explicit_loop_serves_http_websocket_and_reaps_descendants(
    create_app_file: CreateAppFileFixture,
    tmp_project_dir: Path,
) -> None:
    _skip_ineligible_loop()
    _require_capability("tcp")
    _require_capability("websocket")
    app_file = create_app_file(f"event_loop_{_LOOP}.py", content=_APP)
    port = free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_project_dir), env.get("PYTHONPATH", "")))
    env["PYTHONUNBUFFERED"] = "1"
    command = [
        sys.executable,
        "-m",
        "litestar",
        "--app",
        f"{app_file.stem}:app",
        "run",
        "--port",
        str(port),
        "--loop",
        _LOOP,
        "--workers-kill-timeout",
        "1",
    ]
    process = start_process(command, cwd=tmp_project_dir, env=env)

    try:
        wait_for_port(port, process, open_=True)
        descendant_pids = descendants(process.pid)

        with urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            assert response.status == 200
            assert json.load(response) == {"status": "ok"}

        with connect(f"ws://127.0.0.1:{port}/ws", open_timeout=5, close_timeout=5) as websocket_client:
            websocket_client.send(f"echo-{_LOOP}")
            assert websocket_client.recv(timeout=5) == f"echo-{_LOOP}"

        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.kill(process.pid, signal.SIGINT)
        output = finish_process(process, timeout=12)
        wait_for_port(port, process, open_=False)

        if sys.platform == "win32" and process.returncode == 1:
            pytest.xfail("Granian on Windows reports exit status 1 after CTRL_BREAK worker teardown")
        assert process.returncode == 0, output
        assert "ModuleNotFoundError" not in output
        assert "ImportError" not in output
        assert "unsupported loop" not in output.lower()
        wait_for_descendants_to_exit(descendant_pids, parent_pid=process.pid)
    finally:
        terminate_process_group(process)
