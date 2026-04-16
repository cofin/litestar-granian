"""Phase 2 Task 2.3 — direct-mode reload via spawn-context.

Historical issue: `--reload --no-subprocess` silently upgraded to subprocess
mode because fork-workers inherit the parent's `sys.modules` and never see
source changes. Fix: force `multiprocessing` start method to ``spawn`` when
reload is active so each worker respawn is a fresh interpreter.

These tests assert the spawn context is set; they do not spawn real workers.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from granian.constants import HTTPModes, Loops, RuntimeModes, SSLProtocols, TaskImpl
from granian.log import LogLevels

from litestar_granian import cli as granian_cli


def _base_direct_kwargs(**overrides: Any) -> dict[str, Any]:
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
        "reload": True,
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


def test_direct_mode_reload_uses_spawn_context() -> None:
    """With reload=True, ``multiprocessing`` start method must be ``spawn``.

    Fork-workers inherit parent sys.modules, so the app is never reloaded from
    disk after the first import. Spawn workers are fresh processes — reload
    actually picks up source changes.
    """
    with patch.object(granian_cli, "Granian") as mock_granian:
        mock_granian.return_value.serve = MagicMock()
        granian_cli._run_granian(**_base_direct_kwargs(reload=True))
    assert multiprocessing.get_start_method(allow_none=False) == "spawn"


def test_direct_mode_no_reload_leaves_spawn_context_alone() -> None:
    """Without reload, we must not impose spawn on other multiprocessing users."""
    # Save whatever the test runner set
    original = multiprocessing.get_start_method(allow_none=False)
    with patch.object(granian_cli, "Granian") as mock_granian:
        mock_granian.return_value.serve = MagicMock()
        granian_cli._run_granian(**_base_direct_kwargs(reload=False))
    assert multiprocessing.get_start_method(allow_none=False) == original


def test_reload_force_is_gone_from_run_command() -> None:
    """Guard against re-introducing the silent ``reload → in_subprocess=True`` flip.

    The source of ``run_command`` must not contain the pattern that used to
    override the user's explicit ``--no-subprocess`` when ``--reload`` was set.
    """
    import inspect

    # ``run_command`` is a click-wrapped ``RichCommand``; read the callback.
    callback = granian_cli.run_command.callback  # type: ignore[attr-defined]
    source = inspect.getsource(callback)
    # The fixed code sets the spawn context; it must not clobber in_subprocess.
    assert "in_subprocess = True" not in source
