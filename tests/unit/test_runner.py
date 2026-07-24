from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace

import pytest
from watchfiles import Change

from litestar_granian._runner import _probe_granian_compatibility, _ReloadPatternFilter


def test_reload_filter_matches_litestar_uvicorn_include_and_exclude_globs() -> None:
    reload_filter = _ReloadPatternFilter(
        includes=("*.html",),
        excludes=("*.tmp", "ignored/*"),
    )

    assert reload_filter(Change.modified, str(Path("/app/module.py")))
    assert reload_filter(Change.modified, str(Path("/app/template.html")))
    assert not reload_filter(Change.modified, str(Path("/app/notes.txt")))
    assert not reload_filter(Change.modified, str(Path("/app/module.tmp")))
    assert not reload_filter(Change.modified, str(Path("/app/ignored/module.py")))


def test_probe_passes_against_the_installed_granian_release() -> None:
    import granian.cli

    _probe_granian_compatibility(granian.cli)


def test_probe_fails_when_entrypoint_is_missing() -> None:
    import granian.cli

    stub = SimpleNamespace(Server=granian.cli.Server)  # pyright: ignore[reportPrivateImportUsage]

    with pytest.raises(SystemExit) as exc_info:
        _probe_granian_compatibility(stub)

    message = str(exc_info.value)
    assert "granian.cli.entrypoint is missing" in message
    assert version("granian") in message
    assert "granian==2.7.*" in message
    assert "--fd/--reload-include/--reload-exclude" in message


def test_probe_fails_when_server_no_longer_exposes_init_shared_socket() -> None:
    import granian.cli

    stub = SimpleNamespace(entrypoint=granian.cli.entrypoint, Server=type("StubServer", (), {}))

    with pytest.raises(SystemExit) as exc_info:
        _probe_granian_compatibility(stub)

    assert "StubServer._init_shared_socket is missing" in str(exc_info.value)


def test_probe_fails_when_socket_holder_signature_is_incompatible(monkeypatch: pytest.MonkeyPatch) -> None:
    import granian._granian
    import granian.cli

    monkeypatch.setattr(granian._granian, "SocketHolder", lambda _fd: None)

    with pytest.raises(SystemExit) as exc_info:
        _probe_granian_compatibility(granian.cli)

    assert "granian._granian.SocketHolder no longer accepts (fd, uds, backlog)" in str(exc_info.value)


def test_probe_fails_when_socket_holder_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import granian.cli

    monkeypatch.delattr("granian._granian.SocketHolder")

    with pytest.raises(SystemExit) as exc_info:
        _probe_granian_compatibility(granian.cli)

    assert "granian._granian.SocketHolder is missing" in str(exc_info.value)
