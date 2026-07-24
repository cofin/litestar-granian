from __future__ import annotations

import json
import os
import signal
import sys
import urllib.request
from pathlib import Path

from tests.integration._runtime import (
    descendants,
    free_port,
    start_process,
    terminate_process_group,
    wait_for_descendants_to_exit,
    wait_for_port,
)

_ROOT = Path(__file__).parents[2]


def test_documented_app_runs_through_the_real_supervisor() -> None:
    port = free_port()
    command = [
        sys.executable,
        "-m",
        "litestar",
        "--app",
        "docs.examples.app:app",
        "run",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--loop",
        "asyncio",
        "--log-config",
        "docs/examples/logging.json",
        "--static-path-route",
        "/assets",
        "--static-path-mount",
        "docs/examples/static",
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(_ROOT), environment.get("PYTHONPATH", "")]))
    environment["PYTHONUNBUFFERED"] = "1"
    process = start_process(command, cwd=_ROOT, env=environment)

    try:
        wait_for_port(port, process, open_=True)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            assert response.status == 200
            assert json.load(response) == {"hello": "world"}
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/assets/index.html", timeout=5) as response:
            assert response.status == 200
            assert response.read().decode().strip() == "hello from static"

        child_pids = descendants(process.pid)
        assert child_pids
        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.kill(process.pid, signal.SIGINT)
        assert process.wait(timeout=20) == 0
        wait_for_port(port, process, open_=False)
        wait_for_descendants_to_exit(child_pids)
    finally:
        terminate_process_group(process)
