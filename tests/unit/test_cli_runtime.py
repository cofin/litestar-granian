from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from litestar_granian import cli
from litestar_granian.command import _GranianCommand


def test_supervised_runtime_keeps_handlers_and_app_env_through_lifespan_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str | None, str | None, bool]] = []
    installed = False

    class Forwarder:
        def __init__(self, _supervisor: object) -> None:
            pass

        def install(self) -> None:
            nonlocal installed
            installed = True

        def restore(self) -> None:
            nonlocal installed
            installed = False

    @contextmanager
    def lifespan(_app: object) -> Iterator[None]:
        events.append(("enter", os.environ.get("LITESTAR_APP"), os.environ.get("LITESTAR_PORT"), installed))
        try:
            yield
        finally:
            events.append(("exit", os.environ.get("LITESTAR_APP"), os.environ.get("LITESTAR_PORT"), installed))

    supervisor = MagicMock()
    supervisor.run.return_value = 7
    monkeypatch.setattr(cli, "_GranianSupervisor", MagicMock(return_value=supervisor))
    monkeypatch.setattr(cli, "_SignalForwarder", Forwarder)
    monkeypatch.setattr(cli, "_server_lifespan", lifespan)
    monkeypatch.setenv("LITESTAR_APP", "previous:app")
    monkeypatch.setenv("LITESTAR_PORT", "8123")
    built = SimpleNamespace(argv=["granian"], cleanup=MagicMock(), environment={}, pass_fds=())
    env: Any = SimpleNamespace(app=object(), app_path="resolved:app")

    exit_code = cli._run_supervised(env, built, workers_kill_timeout=5, port=9000)

    assert exit_code == 7
    assert events == [
        ("enter", "resolved:app", "9000", False),
        ("exit", "resolved:app", "9000", True),
    ]
    assert os.environ["LITESTAR_APP"] == "previous:app"
    assert os.environ["LITESTAR_PORT"] == "8123"
    assert installed is False
    built.cleanup.assert_called_once()


def test_supervised_runtime_restores_state_after_child_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def lifespan(_app: object) -> Iterator[None]:
        yield

    supervisor = MagicMock()
    supervisor.run.side_effect = RuntimeError("child failed")
    forwarder = MagicMock()
    monkeypatch.setattr(cli, "_GranianSupervisor", MagicMock(return_value=supervisor))
    monkeypatch.setattr(cli, "_SignalForwarder", MagicMock(return_value=forwarder))
    monkeypatch.setattr(cli, "_server_lifespan", lifespan)
    monkeypatch.delenv("LITESTAR_APP", raising=False)
    monkeypatch.delenv("LITESTAR_PORT", raising=False)
    built = SimpleNamespace(argv=["granian"], cleanup=MagicMock(), environment={}, pass_fds=())
    env: Any = SimpleNamespace(app=object(), app_path="resolved:app")

    with pytest.raises(RuntimeError, match="child failed"):
        cli._run_supervised(env, built, workers_kill_timeout=5, port=9000)

    assert "LITESTAR_APP" not in os.environ
    assert "LITESTAR_PORT" not in os.environ
    forwarder.restore.assert_called_once()
    built.cleanup.assert_called_once()


def test_supervised_runtime_removes_generated_log_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    @contextmanager
    def lifespan(_app: object) -> Iterator[None]:
        yield

    config_path = tmp_path / "generated-log-config.json"
    config_path.write_text('{"version": 1}')
    supervisor = MagicMock()
    supervisor.run.return_value = 0
    monkeypatch.setattr(cli, "_GranianSupervisor", MagicMock(return_value=supervisor))
    monkeypatch.setattr(cli, "_SignalForwarder", MagicMock())
    monkeypatch.setattr(cli, "_server_lifespan", lifespan)
    built = _GranianCommand(["granian"], (config_path,))
    env: Any = SimpleNamespace(app=object(), app_path="resolved:app")

    assert cli._run_supervised(env, built, workers_kill_timeout=5, port=9000) == 0
    assert not config_path.exists()


def test_supervised_runtime_removes_generated_config_if_supervisor_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "generated-log-config.json"
    config_path.write_text('{"version": 1}')
    monkeypatch.setattr(cli, "_GranianSupervisor", MagicMock(side_effect=RuntimeError("supervisor setup failed")))
    built = _GranianCommand(["granian"], (config_path,))
    env: Any = SimpleNamespace(app=object(), app_path="resolved:app")

    with pytest.raises(RuntimeError, match="supervisor setup failed"):
        cli._run_supervised(env, built, workers_kill_timeout=5, port=9000)

    assert not config_path.exists()


def test_supervised_runtime_removes_generated_config_if_lifespan_entry_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "generated-log-config.json"
    config_path.write_text('{"version": 1}')
    lifespan = MagicMock()
    lifespan.__enter__.side_effect = RuntimeError("lifespan failed")
    monkeypatch.setattr(cli, "_server_lifespan", MagicMock(return_value=lifespan))
    built = _GranianCommand(["granian"], (config_path,))
    env: Any = SimpleNamespace(app=object(), app_path="resolved:app")

    with pytest.raises(RuntimeError, match="lifespan failed"):
        cli._run_supervised(env, built, workers_kill_timeout=5, port=9000)

    assert not config_path.exists()
