from __future__ import annotations

import os
import signal
import subprocess
from unittest.mock import MagicMock

import pytest

from litestar_granian.supervisor import (
    _CREATE_NEW_PROCESS_GROUP,
    _GranianSupervisor,
    _map_exit_code,
    _SignalForwarder,
)


def test_supervisor_starts_new_posix_session(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123, returncode=0)
    process.wait.return_value = 0
    popen = MagicMock(return_value=process)
    monkeypatch.setattr(subprocess, "Popen", popen)

    exit_code = _GranianSupervisor(["python", "-m", "granian", "app:app"], kill_timeout=5).run()

    assert exit_code == 0
    popen.assert_called_once_with(
        ["python", "-m", "granian", "app:app"],
        start_new_session=True,
    )


def test_supervisor_passes_child_environment_and_file_descriptors(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123, returncode=0)
    process.wait.return_value = 0
    popen = MagicMock(return_value=process)
    monkeypatch.setattr(subprocess, "Popen", popen)

    exit_code = _GranianSupervisor(
        ["python", "-m", "litestar_granian._runner", "app:app"],
        kill_timeout=5,
        environment={"COMPAT": "1"},
        pass_fds=(7,),
    ).run()

    assert exit_code == 0
    child_environment = popen.call_args.kwargs["env"]
    assert child_environment["COMPAT"] == "1"
    assert popen.call_args.kwargs["pass_fds"] == (7,)


def test_pending_termination_signal_is_forwarded_after_child_attachment(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123, returncode=0)
    process.wait.return_value = 0
    popen = MagicMock(return_value=process)
    killpg = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(os, "killpg", killpg)

    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor.forward(signal.SIGTERM)
    supervisor.run()

    killpg.assert_called_once_with(123, signal.SIGTERM)


def test_repeated_termination_signal_kills_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    killpg = MagicMock()
    monkeypatch.setattr(os, "killpg", killpg)
    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor._process = process

    supervisor.forward(signal.SIGINT)
    supervisor.forward(signal.SIGTERM)

    assert killpg.call_args_list == [
        ((123, signal.SIGINT),),
        ((123, signal.SIGKILL),),
    ]


@pytest.mark.skipif(not hasattr(signal, "SIGHUP"), reason="POSIX only")
def test_sighup_is_forwarded_without_starting_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    killpg = MagicMock()
    monkeypatch.setattr(os, "killpg", killpg)
    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor._process = process

    supervisor.forward(signal.SIGHUP)

    killpg.assert_called_once_with(123, signal.SIGHUP)
    assert supervisor.deadline is None


def test_expired_deadline_kills_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    process.wait.side_effect = [subprocess.TimeoutExpired("granian", 0.1), -signal.SIGKILL]
    popen = MagicMock(return_value=process)
    killpg = MagicMock()
    monotonic = MagicMock(side_effect=[10.0, 21.0])
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr("litestar_granian.supervisor.time.monotonic", monotonic)

    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor.forward(signal.SIGTERM)
    exit_code = supervisor.run()

    assert exit_code == 128 + signal.SIGKILL
    assert killpg.call_args_list == [
        ((123, signal.SIGTERM),),
        ((123, signal.SIGKILL),),
    ]


def test_windows_uses_process_group_and_list_taskkill(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=456)
    process.wait.return_value = 1
    popen = MagicMock(return_value=process)
    taskkill = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(subprocess, "run", taskkill)
    monkeypatch.setattr(
        "litestar_granian.supervisor.shutil.which",
        MagicMock(return_value=r"C:\Windows\System32\taskkill.exe"),
    )

    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5, platform="win32")
    supervisor._process = process
    supervisor.forward(signal.SIGTERM)
    supervisor.forward(signal.SIGTERM)
    supervisor._process = None
    exit_code = supervisor.run()

    assert exit_code == 1
    popen.assert_called_once_with(
        ["granian", "app:app"],
        creationflags=_CREATE_NEW_PROCESS_GROUP,
    )
    taskkill.assert_called_once_with(
        [r"C:\Windows\System32\taskkill.exe", "/PID", "456", "/T", "/F"],
        check=False,
    )


def test_signal_forwarder_restores_every_installed_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = MagicMock()
    original = object()
    signal_api = MagicMock(return_value=original)
    monkeypatch.setattr(signal, "signal", signal_api)
    forwarder = _SignalForwarder(supervisor)

    forwarder.install()
    forwarder.restore()

    installed = [call.args[0] for call in signal_api.call_args_list[: len(forwarder.signals)]]
    restored = signal_api.call_args_list[len(forwarder.signals) :]
    assert installed == list(forwarder.signals)
    assert [call.args for call in restored] == [(signum, original) for signum in forwarder.signals]


@pytest.mark.parametrize(
    ("returncode", "expected"),
    [(0, 0), (3, 3), (-signal.SIGTERM, 128 + signal.SIGTERM)],
)
def test_exit_code_mapping(returncode: int, expected: int) -> None:
    assert _map_exit_code(returncode) == expected
