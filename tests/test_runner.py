from __future__ import annotations

from pathlib import Path

from watchfiles import Change

from litestar_granian._runner import _LitestarReloadFilter


def test_reload_filter_matches_litestar_uvicorn_include_and_exclude_globs() -> None:
    reload_filter = _LitestarReloadFilter(
        includes=("*.html",),
        excludes=("*.tmp", "ignored/*"),
    )

    assert reload_filter(Change.modified, str(Path("/app/module.py")))
    assert reload_filter(Change.modified, str(Path("/app/template.html")))
    assert not reload_filter(Change.modified, str(Path("/app/notes.txt")))
    assert not reload_filter(Change.modified, str(Path("/app/module.tmp")))
    assert not reload_filter(Change.modified, str(Path("/app/ignored/module.py")))
