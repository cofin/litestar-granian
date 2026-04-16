"""Phase 2 Task 2.2 — signal-propagation verification.

Locks in the commit 7299adf fix (double-signal stability) so it cannot regress
as the default mode flips. These tests drive the subprocess launcher with a
mocked ``subprocess.Popen`` and verify the signal handlers invoked.
"""

from __future__ import annotations

import signal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from granian.constants import HTTPModes, Loops, RuntimeModes, SSLProtocols, TaskImpl
from granian.log import LogLevels

from litestar_granian import cli as granian_cli


def _kwargs(**overrides: Any) -> dict[str, Any]:
    env = MagicMock()
    env.app.logging_config = None
    env.app_path = "app:app"
    env.is_app_factory = False
    base: dict[str, Any] = {
        "env": env,
        "host": "127.0.0.1",
        "port": 8000,
        "uds": None,
        "uds_permissions": None,
        "http": HTTPModes.auto,
        "wc": 1,
        "blocking_threads": None,
        "blocking_threads_idle_timeout": 30,
        "runtime_threads": 1,
        "runtime_blocking_threads": None,
        "runtime_mode": RuntimeModes.st,
        "loop": Loops.auto,
        "task_impl": TaskImpl.asyncio,
        "backlog": 1024,
        "backpressure": None,
        "http1_buffer_size": 8192,
        "http1_header_read_timeout": 30000,
        "http1_keep_alive": True,
        "http1_pipeline_flush": False,
        "http2_adaptive_window": False,
        "http2_initial_connection_window_size": 1048576,
        "http2_initial_stream_window_size": 1048576,
        "http2_keep_alive_interval": None,
        "http2_keep_alive_timeout": 20,
        "http2_max_concurrent_streams": 200,
        "http2_max_frame_size": 16384,
        "http2_max_headers_size": 16384,
        "http2_max_send_buffer_size": 400000,
        "log_enabled": True,
        "log_access_enabled": False,
        "log_access_fmt": None,
        "log_level": LogLevels.info,
        "ssl_certificate": None,
        "ssl_keyfile": None,
        "ssl_keyfile_password": None,
        "ssl_protocol_min": SSLProtocols.tls13,
        "ssl_ca": None,
        "ssl_crl": None,
        "ssl_client_verify": False,
        "url_path_prefix": None,
        "respawn_failed_workers": False,
        "respawn_interval": 3.5,
        "workers_lifetime": None,
        "workers_kill_timeout": None,
        "workers_max_rss": None,
        "rss_sample_interval": 30,
        "rss_samples": 1,
        "reload": False,
        "reload_paths": None,
        "reload_ignore_dirs": None,
        "reload_ignore_patterns": None,
        "reload_ignore_paths": None,
        "reload_tick": 50,
        "reload_ignore_worker_failure": False,
        "process_name": None,
        "pid_file": None,
        "static_path_route": "/static",
        "static_path_mount": None,
        "static_path_expires": 86400,
        "ws_enabled": True,
        "use_litestar_logger": False,
    }
    base.update(overrides)
    return base


def test_subprocess_sigint_is_ignored_in_parent() -> None:
    """Parent sets SIGINT to SIG_IGN so the child handles Ctrl+C.

    Without this, both parent and child would react to the same SIGINT,
    producing the double-signal instability fixed in 7299adf.
    """
    calls: list[tuple[Any, Any]] = []

    def fake_signal(sig: Any, handler: Any) -> Any:
        calls.append((sig, handler))
        return signal.SIG_DFL

    with (
        patch.object(granian_cli.subprocess, "Popen") as mock_popen,
        patch.object(granian_cli.signal, "signal", side_effect=fake_signal) as _mock_signal,
    ):
        proc = mock_popen.return_value
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        granian_cli._run_granian_in_subprocess(**_kwargs())

    # First call must install SIG_IGN for SIGINT.
    assert calls, "signal.signal was never called"
    sig, handler = calls[0]
    assert sig == signal.SIGINT
    assert handler == signal.SIG_IGN

    # Last call must restore the original handler to avoid leaking state.
    restored_sig, restored_handler = calls[-1]
    assert restored_sig == signal.SIGINT
    assert restored_handler == signal.SIG_DFL


def test_subprocess_is_terminated_if_still_running() -> None:
    """If the child is still alive after wait() unwinds, the parent reaps it."""
    with (
        patch.object(granian_cli.subprocess, "Popen") as mock_popen,
        patch.object(granian_cli.signal, "signal"),
    ):
        proc = mock_popen.return_value
        proc.wait.return_value = 0
        # First poll: still running → triggers terminate. Second poll after terminate: reaped.
        proc.poll.side_effect = [None, 0]
        granian_cli._run_granian_in_subprocess(**_kwargs())

    proc.terminate.assert_called_once()


def test_subprocess_keyboard_interrupt_sends_sigterm_on_unix() -> None:
    """On POSIX, a KeyboardInterrupt during ``wait()`` must escalate to SIGTERM."""
    with (
        patch.object(granian_cli.subprocess, "Popen") as mock_popen,
        patch.object(granian_cli.signal, "signal"),
        patch.object(granian_cli.platform, "system", return_value="Linux"),
    ):
        proc = mock_popen.return_value
        proc.wait.side_effect = KeyboardInterrupt()
        proc.poll.return_value = 0
        granian_cli._run_granian_in_subprocess(**_kwargs())

    proc.send_signal.assert_called_with(signal.SIGTERM)


def test_log_config_tempfile_is_cleaned_up_on_normal_exit(tmp_path: Path) -> None:
    """When --use-litestar-logger is set, the temp log-config file must be
    removed when the subprocess exits."""
    from litestar.logging.config import LoggingConfig

    env = MagicMock()
    env.app.logging_config = LoggingConfig(loggers={})
    env.app_path = "app:app"
    env.is_app_factory = False

    created: list[str] = []

    real_mkstemp = granian_cli.tempfile.mkstemp

    def tracking_mkstemp(*args: Any, **kwargs: Any) -> Any:
        fd, path = real_mkstemp(*args, **kwargs)
        created.append(path)
        return fd, path

    with (
        patch.object(granian_cli.subprocess, "Popen") as mock_popen,
        patch.object(granian_cli.signal, "signal"),
        patch.object(granian_cli.tempfile, "mkstemp", side_effect=tracking_mkstemp),
    ):
        proc = mock_popen.return_value
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        granian_cli._run_granian_in_subprocess(**_kwargs(env=env, use_litestar_logger=True))

    assert created, "expected a log-config temp file to be created"
    for path in created:
        assert not Path(path).exists(), f"temp file {path} was not cleaned up"
