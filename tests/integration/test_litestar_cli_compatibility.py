from __future__ import annotations

import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="inherited file descriptors are POSIX-only")
def test_file_descriptor_serves_requests_through_supervised_granian() -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        listener.set_inheritable(True)
        port = int(listener.getsockname()[1])
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "litestar",
                "--app",
                "docs.examples.app:app",
                "run",
                "--fd",
                str(listener.fileno()),
                "--granian-no-log",
            ],
            pass_fds=(listener.fileno(),),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=Path(__file__).parents[2],
        )
        try:
            response = _request_when_ready(process, port)
            assert response.startswith(b"HTTP/1.1 200 OK")
            assert b'"hello":"world"' in response
        finally:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def _request_when_ready(process: subprocess.Popen[str], port: int) -> bytes:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            message = f"server exited before readiness ({process.returncode}):\n{output}"
            raise AssertionError(message)
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2) as client:
                client.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
                response = b""
                while chunk := client.recv(4096):
                    response += chunk
                return response
        except OSError:
            time.sleep(0.05)
    msg = f"server did not accept inherited socket on port {port}"
    raise AssertionError(msg)
