"""Supervise one fresh Granian child process group and forward signals."""

import os
import shutil
import signal
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from types import FrameType
from typing import Any

_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
_POLL_INTERVAL = 0.1


def _map_exit_code(returncode: int) -> int:
    """Translate a POSIX signal return code to the conventional shell status.

    Returns:
        The child status, with signal exits normalized to ``128 + signal``.
    """
    return 128 + abs(returncode) if returncode < 0 else returncode


class _GranianSupervisor:
    """Supervise a fresh Granian process group from the Litestar CLI parent."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        kill_timeout: float,
        environment: dict[str, str] | None = None,
        pass_fds: tuple[int, ...] = (),
        platform: str = sys.platform,
    ) -> None:
        self.command = list(command)
        self.kill_timeout = kill_timeout
        self.environment = environment or {}
        self.pass_fds = pass_fds
        self.platform = platform
        self.deadline: float | None = None
        self._process: subprocess.Popen[Any] | None = None
        self._pending_signals: list[int] = []
        self._termination_forwarded = False
        self._killed = False

    def run(self) -> int:
        """Start Granian and wait for it.

        Returns:
            The normalized Granian exit status.
        """
        popen_kwargs: dict[str, Any] = {}
        if self.environment:
            popen_kwargs["env"] = {**os.environ, **self.environment}
        if self.platform == "win32":
            popen_kwargs["creationflags"] = _CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
            if self.pass_fds:
                popen_kwargs["pass_fds"] = self.pass_fds
        process = subprocess.Popen(self.command, **popen_kwargs)
        self._process = process
        pending_signals, self._pending_signals = self._pending_signals, []
        for signum in pending_signals:
            self.forward(signum)

        while True:
            try:
                return _map_exit_code(process.wait(timeout=_POLL_INTERVAL))
            except subprocess.TimeoutExpired:
                if self.deadline is not None and time.monotonic() >= self.deadline:
                    self._kill_group()

    def forward(self, signum: int) -> None:
        """Forward a signal or queue it until the child process is attached."""
        if self._process is None:
            self._pending_signals.append(signum)
            return

        if hasattr(signal, "SIGHUP") and signum == signal.SIGHUP:
            self._send_group_signal(signum)
            return

        is_windows_break = self.platform == "win32" and signum == getattr(signal, "SIGBREAK", None)
        if signum not in {signal.SIGINT, signal.SIGTERM} and not is_windows_break:
            self._send_group_signal(signum)
            return

        if self._termination_forwarded:
            self._kill_group()
            return

        self._termination_forwarded = True
        self._send_group_signal(signum)
        self.deadline = time.monotonic() + self.kill_timeout + 5

    def _send_group_signal(self, signum: int) -> None:
        process = self._process
        if process is None:
            return
        if self.platform == "win32":
            process.send_signal(getattr(signal, "CTRL_BREAK_EVENT", signal.SIGTERM))
        else:
            os.killpg(process.pid, signum)

    def _kill_group(self) -> None:
        process = self._process
        if process is None or self._killed:
            return
        self._killed = True
        if self.platform == "win32":
            taskkill = shutil.which("taskkill") or str(
                Path(os.environ.get("SYSTEMROOT", "C:\\Windows")) / "System32" / "taskkill.exe"
            )
            subprocess.run(
                [taskkill, "/PID", str(process.pid), "/T", "/F"],
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)


class _SignalForwarder:
    """Install temporary parent handlers that delegate to a supervisor."""

    def __init__(self, supervisor: _GranianSupervisor) -> None:
        self.supervisor = supervisor
        self.signals = (
            (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
            if hasattr(signal, "SIGHUP")
            else (signal.SIGINT, signal.SIGTERM, signal.SIGBREAK)  # type: ignore[attr-defined]
        )
        self._original_handlers: dict[int, Any] = {}

    def install(self) -> None:
        """Install forwarding handlers for the current platform."""
        for signum in self.signals:
            self._original_handlers[signum] = signal.signal(signum, self._handle)

    def restore(self) -> None:
        """Restore all handlers saved by :meth:`install`."""
        for signum in self.signals:
            original = self._original_handlers.get(signum)
            if original is not None:
                signal.signal(signum, original)
        self._original_handlers.clear()

    def _handle(self, signum: int, _frame: FrameType | None) -> None:
        self.supervisor.forward(signum)
