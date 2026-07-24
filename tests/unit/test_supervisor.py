from __future__ import annotations

import os
import signal
import subprocess
from typing import Any
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
    process.wait.assert_called_once_with()


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
    process.poll.return_value = None
    popen = MagicMock(return_value=process)
    killpg = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(signal, "setitimer", MagicMock())

    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor.forward(signal.SIGTERM)
    supervisor.run()

    killpg.assert_called_once_with(123, signal.SIGTERM)


def test_repeated_termination_signal_kills_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    process.poll.return_value = None
    killpg = MagicMock()
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(signal, "setitimer", MagicMock())
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
    process.poll.return_value = None
    killpg = MagicMock()
    setitimer = MagicMock()
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(signal, "setitimer", setitimer)
    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor._process = process

    supervisor.forward(signal.SIGHUP)

    killpg.assert_called_once_with(123, signal.SIGHUP)
    assert supervisor.deadline is None
    setitimer.assert_not_called()


def test_first_termination_signal_arms_kill_deadline_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    process.wait.return_value = 0
    process.poll.return_value = None
    setitimer = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(os, "killpg", MagicMock())
    monkeypatch.setattr(signal, "setitimer", setitimer)

    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor.forward(signal.SIGTERM)
    supervisor.run()

    assert [call.args for call in setitimer.call_args_list] == [
        (signal.ITIMER_REAL, 10.0),
        (signal.ITIMER_REAL, 0),
    ]
    assert supervisor.deadline is None


def test_kill_deadline_alarm_kills_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    process.poll.return_value = None
    handlers: dict[int, Any] = {}

    def record_handler(signum: int, handler: Any) -> Any:
        previous = handlers.get(signum)
        handlers[signum] = handler
        return previous

    def expire_deadline(*_args: Any, **_kwargs: Any) -> int:
        handlers[signal.SIGALRM](signal.SIGALRM, None)
        return -signal.SIGKILL

    process.wait.side_effect = expire_deadline
    killpg = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(signal, "signal", MagicMock(side_effect=record_handler))
    monkeypatch.setattr(signal, "setitimer", MagicMock())

    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor.forward(signal.SIGTERM)
    exit_code = supervisor.run()

    assert exit_code == 128 + signal.SIGKILL
    assert killpg.call_args_list == [
        ((123, signal.SIGTERM),),
        ((123, signal.SIGKILL),),
    ]


def test_run_restores_previous_alarm_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    process.wait.return_value = 0
    process.poll.return_value = None
    previous = MagicMock()
    signal_api = MagicMock(return_value=previous)
    setitimer = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(signal, "signal", signal_api)
    monkeypatch.setattr(signal, "setitimer", setitimer)

    _GranianSupervisor(["granian", "app:app"], kill_timeout=5).run()

    installed, restored = signal_api.call_args_list
    assert installed.args[0] == signal.SIGALRM
    assert callable(installed.args[1])
    assert restored.args == (signal.SIGALRM, previous)
    assert [call.args for call in setitimer.call_args_list] == [(signal.ITIMER_REAL, 0)]


def test_run_restores_default_alarm_handler_when_previous_is_foreign(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    process.wait.return_value = 0
    process.poll.return_value = None
    signal_api = MagicMock(return_value=None)
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(signal, "signal", signal_api)
    monkeypatch.setattr(signal, "setitimer", MagicMock())

    _GranianSupervisor(["granian", "app:app"], kill_timeout=5).run()

    assert signal_api.call_args_list[-1].args == (signal.SIGALRM, signal.SIG_DFL)


def test_forward_after_child_exit_leaves_the_reaped_group_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    process.poll.return_value = 0
    killpg = MagicMock()
    setitimer = MagicMock()
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(signal, "setitimer", setitimer)
    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor._process = process

    supervisor.forward(signal.SIGINT)
    supervisor.forward(signal.SIGINT)

    killpg.assert_not_called()
    setitimer.assert_not_called()


def test_kill_group_after_child_exit_leaves_the_reaped_group_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    process.poll.return_value = 0
    killpg = MagicMock()
    monkeypatch.setattr(os, "killpg", killpg)
    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor._process = process

    supervisor._kill_group()

    killpg.assert_not_called()


def test_process_lookup_error_from_killpg_does_not_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    process.poll.return_value = None
    killpg = MagicMock(side_effect=ProcessLookupError)
    monkeypatch.setattr(os, "killpg", killpg)
    monkeypatch.setattr(signal, "setitimer", MagicMock())
    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5)
    supervisor._process = process

    supervisor.forward(signal.SIGTERM)
    supervisor._kill_group()

    assert killpg.call_args_list == [
        ((123, signal.SIGTERM),),
        ((123, signal.SIGKILL),),
    ]


def test_failed_wait_kills_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=123)
    process.wait.side_effect = RuntimeError("wait failed")
    process.poll.return_value = None
    killpg = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=process))
    monkeypatch.setattr(os, "killpg", killpg)

    with pytest.raises(RuntimeError, match="wait failed"):
        _GranianSupervisor(["granian", "app:app"], kill_timeout=5).run()

    killpg.assert_called_once_with(123, signal.SIGKILL)


def test_windows_uses_process_group_and_list_taskkill(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=456)
    process.wait.return_value = 1
    process.poll.return_value = None
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


def test_windows_expired_deadline_kills_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock(pid=456)
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("granian", 0.1), -signal.SIGKILL]
    popen = MagicMock(return_value=process)
    taskkill = MagicMock()
    monotonic = MagicMock(side_effect=[10.0, 21.0])
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(subprocess, "run", taskkill)
    monkeypatch.setattr("litestar_granian.supervisor.time.monotonic", monotonic)
    monkeypatch.setattr(
        "litestar_granian.supervisor.shutil.which",
        MagicMock(return_value=r"C:\Windows\System32\taskkill.exe"),
    )

    supervisor = _GranianSupervisor(["granian", "app:app"], kill_timeout=5, platform="win32")
    supervisor.forward(signal.SIGTERM)
    exit_code = supervisor.run()

    assert exit_code == 128 + signal.SIGKILL
    assert supervisor.deadline == pytest.approx(20.0)
    process.send_signal.assert_called_once()
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
    signal_api.reset_mock()
    forwarder.restore()

    signal_api.assert_not_called()


def test_signal_forwarder_restores_handlers_that_python_did_not_install(monkeypatch: pytest.MonkeyPatch) -> None:
    signal_api = MagicMock(return_value=None)
    monkeypatch.setattr(signal, "signal", signal_api)
    forwarder = _SignalForwarder(MagicMock())

    forwarder.install()
    signal_api.reset_mock()
    forwarder.restore()

    assert [call.args for call in signal_api.call_args_list] == [
        (signum, signal.SIG_DFL) for signum in forwarder.signals
    ]


@pytest.mark.parametrize(
    ("returncode", "expected"),
    [(0, 0), (3, 3), (-signal.SIGTERM, 128 + signal.SIGTERM)],
)
def test_exit_code_mapping(returncode: int, expected: int) -> None:
    assert _map_exit_code(returncode) == expected
