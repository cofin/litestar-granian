"""Unit tests for ``_run_granian_in_subprocess`` argument assembly.

Phase 1 regression tests: exercise the ``process_args`` dict the subprocess
launcher builds, so bugs are caught without spawning real Granian processes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from granian.constants import HTTPModes, Loops, RuntimeModes, SSLProtocols, TaskImpl
from granian.log import LogLevels

from litestar_granian import cli as granian_cli


def _base_kwargs(**overrides: Any) -> dict[str, Any]:
    """Build the minimum viable kwarg set for ``_run_granian_in_subprocess``."""
    env = MagicMock()
    env.app.logging_config = None
    env.app_path = "app:app"
    env.is_app_factory = False
    defaults: dict[str, Any] = {
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
        "static_path_route": (),
        "static_path_mount": (),
        "static_path_dir_to_file": None,
        "static_path_expires": 86400,
        "ws_enabled": True,
        "working_dir": None,
        "env_files": (),
        "log_config": None,
        "metrics_enabled": False,
        "metrics_scrape_interval": 15,
        "metrics_address": "127.0.0.1",
        "metrics_port": 9090,
        "use_litestar_logger": False,
    }
    defaults.update(overrides)
    return defaults


def _capture_process_args(**overrides: Any) -> list[str]:
    """Invoke ``_run_granian_in_subprocess`` with Popen mocked; return CLI argv."""
    with (
        patch.object(granian_cli.subprocess, "Popen") as mock_popen,
        patch.object(granian_cli.signal, "signal") as _mock_signal,
    ):
        mock_popen.return_value.wait.return_value = 0
        mock_popen.return_value.poll.return_value = 0
        granian_cli._run_granian_in_subprocess(**_base_kwargs(**overrides))
    call_args, _ = mock_popen.call_args
    return list(call_args[0])


def test_pid_file_is_stringified_absolute_path(tmp_path: Path) -> None:
    """Phase 1 Task 1.1: ``pid_file`` must be a string path, not a bound method."""
    pid_file = tmp_path / "granian.pid"
    argv = _capture_process_args(pid_file=pid_file)

    pid_args = [a for a in argv if a.startswith("--pid-file=")]
    assert pid_args, "pid-file flag missing"
    (value,) = pid_args
    assert "built-in method" not in value
    assert value.endswith("granian.pid")


def test_respawn_failed_workers_is_forwarded() -> None:
    """Phase 1 Task 1.2: ``--respawn-failed-workers`` must land in argv."""
    argv = _capture_process_args(respawn_failed_workers=True, respawn_interval=5.0)
    assert "--respawn-failed-workers" in argv
    assert any(a.startswith("--respawn-interval=5.0") for a in argv)


def test_respawn_interval_forwarded_even_without_respawn_flag() -> None:
    """The interval alone should still pass through (backward compat)."""
    argv = _capture_process_args(respawn_failed_workers=False, respawn_interval=7.5)
    assert any(a.startswith("--respawn-interval=7.5") for a in argv)
    assert "--respawn-failed-workers" not in argv


def test_blocking_threads_idle_timeout_always_forwarded() -> None:
    """Phase 1 Task 1.3: no guard — value has non-None default, always pass."""
    argv = _capture_process_args(blocking_threads_idle_timeout=45)
    assert any(a.startswith("--blocking-threads-idle-timeout=45") for a in argv)


def test_runtime_threads_always_forwarded() -> None:
    argv = _capture_process_args(runtime_threads=4)
    assert any(a.startswith("--runtime-threads=4") for a in argv)


def test_use_litestar_logger_forwards_log_config(tmp_path: Path) -> None:
    """Phase 0 Task 0.4: subprocess mode receives a --log-config temp file."""
    from litestar.logging.config import LoggingConfig

    env = MagicMock()
    env.app.logging_config = LoggingConfig(loggers={})
    env.app_path = "app:app"
    env.is_app_factory = False
    argv = _capture_process_args(env=env, use_litestar_logger=True)
    log_config_args = [a for a in argv if a.startswith("--log-config=")]
    assert log_config_args, f"expected --log-config in argv, got: {argv}"
