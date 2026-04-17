"""Phase 5 — Uvicorn-compatible CLI aliases (issue #61)."""

from __future__ import annotations

from click.testing import CliRunner

from litestar_granian.cli import run_command


def test_help_exposes_uvicorn_aliases() -> None:
    runner = CliRunner()
    result = runner.invoke(run_command, ["--help"], terminal_width=200)
    assert result.exit_code == 0
    for alias in ("--reload-exclude", "--reload-include", "--ssl-certfile", "--ssl-keyfile"):
        assert alias in result.output, f"{alias} missing from --help"


def test_ssl_certfile_alias_parses(tmp_path) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    (tmp_path / "c.pem").write_text("x")
    (tmp_path / "k.pem").write_text("x")
    result = runner.invoke(
        run_command,
        [
            "--ssl-certfile",
            str(tmp_path / "c.pem"),
            "--ssl-keyfile",
            str(tmp_path / "k.pem"),
            "--help",
        ],
        terminal_width=200,
    )
    assert result.exit_code == 0


def test_reload_include_exclude_aliases_parse() -> None:
    runner = CliRunner()
    result = runner.invoke(
        run_command,
        [
            "--reload-include",
            ".",
            "--reload-exclude",
            "build",
            "--help",
        ],
        terminal_width=200,
    )
    assert result.exit_code == 0
