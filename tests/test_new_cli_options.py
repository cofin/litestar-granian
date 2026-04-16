"""Phase 3 — Granian 2.7.x feature-parity CLI options."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from litestar_granian import cli as granian_cli
from litestar_granian.cli import run_command
from tests.test_subprocess_args import _base_kwargs, _capture_process_args


def test_working_dir_forwarded_to_server_args(tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    with patch.object(granian_cli, "Granian") as mock_granian:
        mock_granian.return_value.serve = MagicMock()
        granian_cli._run_granian(**_direct_kwargs(working_dir=workdir))
    _, kwargs = mock_granian.call_args
    assert kwargs["working_dir"] == workdir


def test_env_files_forwarded_to_server_args(tmp_path: Path) -> None:
    env_a = tmp_path / ".env.a"
    env_a.write_text("X=1")
    env_b = tmp_path / ".env.b"
    env_b.write_text("Y=2")
    with patch.object(granian_cli, "Granian") as mock_granian:
        mock_granian.return_value.serve = MagicMock()
        granian_cli._run_granian(**_direct_kwargs(env_files=(env_a, env_b)))
    _, kwargs = mock_granian.call_args
    assert [p.name for p in kwargs["env_files"]] == [".env.a", ".env.b"]


def test_metrics_enabled_forwards_metrics_args() -> None:
    with patch.object(granian_cli, "Granian") as mock_granian:
        mock_granian.return_value.serve = MagicMock()
        granian_cli._run_granian(
            **_direct_kwargs(
                metrics_enabled=True,
                metrics_scrape_interval=30,
                metrics_address="0.0.0.0",
                metrics_port=9191,
            )
        )
    _, kwargs = mock_granian.call_args
    assert kwargs["metrics_enabled"] is True
    assert kwargs["metrics_scrape_interval"] == 30
    assert kwargs["metrics_address"] == "0.0.0.0"
    assert kwargs["metrics_port"] == 9191


def test_static_multi_mount_routes_and_paths(tmp_path: Path) -> None:
    d1 = tmp_path / "a"
    d2 = tmp_path / "b"
    d1.mkdir()
    d2.mkdir()
    with patch.object(granian_cli, "Granian") as mock_granian:
        mock_granian.return_value.serve = MagicMock()
        granian_cli._run_granian(
            **_direct_kwargs(
                static_path_route=("/a", "/b"),
                static_path_mount=(d1, d2),
                static_path_dir_to_file="index.html",
            )
        )
    _, kwargs = mock_granian.call_args
    assert kwargs["static_path_route"] == ["/a", "/b"]
    assert [p.name for p in kwargs["static_path_mount"]] == ["a", "b"]
    assert kwargs["static_path_dir_to_file"] == "index.html"


def test_log_config_file_wins_over_use_litestar_logger(tmp_path: Path) -> None:
    cfg = tmp_path / "log.json"
    cfg.write_text('{"version": 1, "disable_existing_loggers": false}')
    with patch.object(granian_cli, "Granian") as mock_granian:
        mock_granian.return_value.serve = MagicMock()
        granian_cli._run_granian(**_direct_kwargs(log_config=cfg, use_litestar_logger=True))
    _, kwargs = mock_granian.call_args
    assert kwargs["log_dictconfig"] == {"version": 1, "disable_existing_loggers": False}


def test_subprocess_metrics_forwarded_as_flags() -> None:
    argv = _capture_process_args(
        metrics_enabled=True, metrics_scrape_interval=30, metrics_address="0.0.0.0", metrics_port=9191
    )
    assert "--metrics" in argv
    assert any(a.startswith("--metrics-scrape-interval=30") for a in argv)
    assert any(a.startswith("--metrics-address=0.0.0.0") for a in argv)
    assert any(a.startswith("--metrics-port=9191") for a in argv)


def test_subprocess_working_dir_and_env_files(tmp_path: Path) -> None:
    workdir = tmp_path / "w"
    workdir.mkdir()
    env_a = tmp_path / ".env"
    env_a.write_text("X=1")
    argv = _capture_process_args(working_dir=workdir, env_files=(env_a,))
    assert any(a.startswith("--working-dir=") and "/w" in a for a in argv)
    assert any(a.startswith("--env-files=") and ".env" in a for a in argv)


def test_subprocess_user_log_config_beats_use_litestar_logger(tmp_path: Path) -> None:
    cfg = tmp_path / "log.json"
    cfg.write_text('{"version": 1}')
    argv = _capture_process_args(log_config=cfg, use_litestar_logger=True)
    log_cfg_args = [a for a in argv if a.startswith("--log-config=")]
    assert len(log_cfg_args) == 1
    assert str(cfg.absolute()) in log_cfg_args[0]


def test_help_lists_all_new_options() -> None:
    runner = CliRunner()
    result = runner.invoke(run_command, ["--help"], terminal_width=200)
    assert result.exit_code == 0
    for flag in (
        "--working-dir",
        "--env-files",
        "--log-config",
        "--static-path-dir-to-file",
        "--metrics",
        "--metrics-scrape-interval",
        "--metrics-address",
        "--metrics-port",
    ):
        assert flag in result.output, f"{flag} missing from --help"


def _direct_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs = _base_kwargs(**overrides)
    return {k: v for k, v in kwargs.items() if k in _direct_signature_params()}


def _direct_signature_params() -> set[str]:
    import inspect

    return set(inspect.signature(granian_cli._run_granian).parameters)
