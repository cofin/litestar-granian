from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from litestar_granian import cli

if TYPE_CHECKING:
    from pathlib import Path

    from click.testing import CliRunner
    from litestar.cli._utils import LitestarGroup  # pyright: ignore[reportPrivateImportUsage]

    from tests.conftest import CreateAppFileFixture


def test_root_cli_invokes_the_supervised_runtime(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)
    monkeypatch.delenv("LITESTAR_PORT", raising=False)

    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run", "--port", "9876", "--workers", "999"],
    )

    assert result.exit_code == 0, result.output
    built = run_supervised.call_args.args[1]
    assert "--port=9876" in built.argv
    assert "--workers=999" in built.argv


def test_litestar_environment_wins_over_granian_environment(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)

    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run"],
        env={"LITESTAR_HOST": "127.0.0.2", "GRANIAN_HOST": "127.0.0.3"},
    )

    assert result.exit_code == 0, result.output
    assert "--host=127.0.0.2" in run_supervised.call_args.args[1].argv


def test_granian_environment_supplies_shared_option_when_litestar_is_unset(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)
    monkeypatch.delenv("LITESTAR_PORT", raising=False)

    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run"],
        env={"GRANIAN_PORT": "9877"},
    )

    assert result.exit_code == 0, result.output
    assert "--port=9877" in run_supervised.call_args.args[1].argv


def test_metrics_warn_when_litestar_prometheus_is_not_configured(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)

    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run", "--metrics"],
    )

    assert result.exit_code == 0, result.output
    normalized_output = " ".join(result.output.split())
    assert "--metrics enables Granian server and worker metrics only" in normalized_output
    assert "application-level request metrics are not being exported" in normalized_output
    assert "--metrics" in run_supervised.call_args.args[1].argv


def test_metrics_warning_is_suppressed_for_litestar_prometheus(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)
    monkeypatch.setattr(cli, "_has_litestar_prometheus_instrumentation", MagicMock(return_value=True))

    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run", "--metrics"],
    )

    assert result.exit_code == 0, result.output
    assert "--metrics enables Granian server and worker metrics only" not in result.output


@pytest.mark.parametrize(
    ("component_name", "component_module"),
    [
        ("PrometheusMiddleware", "litestar.plugins.prometheus.middleware"),
        ("PrometheusPlugin", "litestar.contrib.prometheus.plugin"),
    ],
)
def test_litestar_prometheus_detection(component_name: str, component_module: str) -> None:
    component_type = type(component_name, (), {"__module__": component_module})
    component = component_type()
    app: Any = (
        SimpleNamespace(middleware=[SimpleNamespace(middleware=component_type)], plugins=[])
        if component_name == "PrometheusMiddleware"
        else SimpleNamespace(middleware=[], plugins=[component])
    )

    assert cli._has_litestar_prometheus_instrumentation(app)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--ssl-client-verify"], "--ssl-client-verify requires --ssl-ca"),
    ],
)
def test_supervised_usage_errors(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    args: list[str],
    message: str,
) -> None:
    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run", *args],
    )

    assert result.exit_code == 2
    assert message in result.output


@pytest.mark.parametrize(
    ("args", "option_name"),
    [
        (["--reload"], "--reload"),
        (["--reload-paths", "."], "--reload"),
        (["--reload-include", "*.html"], "--reload"),
        (["--reload-exclude", "*.tmp"], "--reload"),
        (["--workers-max-rss", "256"], "--workers-max-rss"),
    ],
)
def test_free_threaded_usage_errors_precede_app_and_supervisor_startup(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    option_name: str,
) -> None:
    build_command = MagicMock()
    run_supervised = MagicMock(return_value=0)
    server_lifespan = MagicMock()
    monkeypatch.setattr(cli, "_is_free_threaded_build", lambda: True, raising=False)
    monkeypatch.setattr(cli, "_build_granian_command", build_command)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)
    monkeypatch.setattr(cli, "_server_lifespan", server_lifespan)

    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run", *args],
    )

    assert result.exit_code == 2
    assert f"{option_name} is not supported on free-threaded Python" in result.output
    build_command.assert_not_called()
    run_supervised.assert_not_called()
    server_lifespan.assert_not_called()


def test_ordinary_build_forwards_reload_and_worker_rss(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_is_free_threaded_build", lambda: False, raising=False)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)

    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--reload-include",
            "*.html",
            "--workers-max-rss",
            "256",
        ],
    )

    assert result.exit_code == 0, result.output
    argv = run_supervised.call_args.args[1].argv
    assert "--reload" in argv
    assert "--workers-max-rss=256" in argv


@pytest.mark.parametrize(("args", "env"), [(["--pdb"], {}), ([], {"LITESTAR_PDB": "true"})])
@pytest.mark.filterwarnings("ignore:Python Debugger on exception enabled")
def test_pdb_matches_litestar_run_behavior(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    env: dict[str, str],
) -> None:
    observed: dict[str, object] = {}

    def run_supervised(litestar_env: Any, *_args: object, **_kwargs: object) -> int:
        observed["pdb_env"] = os.getenv("LITESTAR_PDB")
        observed["pdb_on_exception"] = litestar_env.app.pdb_on_exception
        return 0

    monkeypatch.setattr(cli, "_run_supervised", run_supervised)
    monkeypatch.setenv("LITESTAR_PDB", "0")
    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run", *args],
        env=env,
    )

    assert result.exit_code == 0, result.output
    assert observed == {"pdb_env": "1", "pdb_on_exception": True}


def test_reload_dir_alias_is_forwarded(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watched = tmp_path / "watched"
    watched.mkdir()
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_is_free_threaded_build", lambda: False, raising=False)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)

    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run", "-R", str(watched)],
    )

    assert result.exit_code == 0, result.output
    argv = run_supervised.call_args.args[1].argv
    assert f"--reload-paths={watched.resolve()}" in argv
    assert "--reload" in argv


def test_litestar_reload_filters_are_forwarded_and_enable_reload(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_is_free_threaded_build", lambda: False, raising=False)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)

    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "-I",
            "*.html",
            "-E",
            "*.tmp",
        ],
    )

    assert result.exit_code == 0, result.output
    built = run_supervised.call_args.args[1]
    assert "--reload" in built.argv
    assert json.loads(built.environment["LITESTAR_GRANIAN_RELOAD_INCLUDES"]) == ["*.html"]
    assert json.loads(built.environment["LITESTAR_GRANIAN_RELOAD_EXCLUDES"]) == ["*.tmp"]


@pytest.mark.parametrize(
    ("option_name", "expected_warning"),
    [
        ("--in-subprocess", "--in-subprocess/--no-subprocess is deprecated and ignored"),
        ("--no-subprocess", "--in-subprocess/--no-subprocess is deprecated and ignored"),
        ("--use-litestar-logger", "--use-litestar-logger/--no-litestar-logger is deprecated and ignored"),
        ("--no-litestar-logger", "--use-litestar-logger/--no-litestar-logger is deprecated and ignored"),
    ],
)
def test_removed_boolean_options_warn_and_are_ignored(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    option_name: str,
    expected_warning: str,
) -> None:
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)

    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run", option_name],
    )

    assert result.exit_code == 0, result.output
    assert expected_warning in result.output
    argv = run_supervised.call_args.args[1].argv
    assert all("subprocess" not in arg and "litestar-logger" not in arg for arg in argv)


@pytest.mark.parametrize("alias", ["-U", "--unix-domain-socket", "--uds"])
def test_litestar_and_granian_uds_aliases_are_forwarded(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alias: str,
) -> None:
    socket_path = tmp_path / "app.sock"
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)

    result = runner.invoke(
        root_command,
        ["--app", f"{app_file.stem}:app", "run", alias, str(socket_path)],
    )

    assert result.exit_code == 0, result.output
    assert f"--uds={socket_path.resolve()}" in run_supervised.call_args.args[1].argv


@pytest.mark.parametrize(
    "args",
    [
        ["--workers", "0"],
        ["--runtime-threads", "0"],
        ["--backlog", "127"],
        ["--workers-max-rss", "0"],
        ["--workers-lifetime", "59"],
        ["--metrics-port", "0"],
        ["--reload-tick", "49"],
        ["--http", "HTTP2"],
    ],
)
def test_native_range_and_choice_validation(args: list[str]) -> None:
    from click.testing import CliRunner

    result = CliRunner().invoke(cli.run_command, args)

    assert result.exit_code == 2


def test_self_signed_certificate_paths_are_forwarded(
    runner: CliRunner,
    root_command: LitestarGroup,
    create_app_file: CreateAppFileFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_file = create_app_file("ssl_app.py")
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    monkeypatch.setattr(cli, "create_ssl_files", MagicMock(return_value=(str(cert), str(key))))
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)

    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--create-self-signed-cert",
            "--ssl-certificate",
            str(cert),
            "--ssl-keyfile",
            str(key),
        ],
    )

    assert result.exit_code == 0, result.output
    argv = run_supervised.call_args.args[1].argv
    assert f"--ssl-certificate={cert.resolve()}" in argv
    assert f"--ssl-keyfile={key.resolve()}" in argv


def test_ssl_certfile_compatibility_alias_is_forwarded(
    runner: CliRunner,
    root_command: LitestarGroup,
    app_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("cert")
    key.write_text("key")
    run_supervised = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "_run_supervised", run_supervised)

    result = runner.invoke(
        root_command,
        [
            "--app",
            f"{app_file.stem}:app",
            "run",
            "--ssl-certfile",
            str(cert),
            "--ssl-keyfile",
            str(key),
        ],
    )

    assert result.exit_code == 0, result.output
    argv = run_supervised.call_args.args[1].argv
    assert f"--ssl-certificate={cert.resolve()}" in argv
