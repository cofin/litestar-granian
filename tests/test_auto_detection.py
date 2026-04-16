"""Phase 4 — auto-detection helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from litestar import Litestar
from litestar.static_files import StaticFilesConfig

from litestar_granian.cli import _detect_static_from_litestar, _has_prometheus_plugin


def test_detect_static_empty_app() -> None:
    app = Litestar()
    routes, mounts, dir_to_file = _detect_static_from_litestar(app)
    assert routes == []
    assert mounts == []
    assert dir_to_file is None


def test_detect_static_single_entry(tmp_path: Path) -> None:
    d = tmp_path / "assets"
    d.mkdir()
    app = Litestar(static_files_config=[StaticFilesConfig(path="/a", directories=[str(d)])])
    routes, mounts, dir_to_file = _detect_static_from_litestar(app)
    assert routes == ["/a"]
    assert [p.name for p in mounts] == ["assets"]
    assert dir_to_file is None


def test_detect_static_html_mode_sets_index(tmp_path: Path) -> None:
    d = tmp_path / "spa"
    d.mkdir()
    app = Litestar(static_files_config=[StaticFilesConfig(path="/", directories=[str(d)], html_mode=True)])
    _, _, dir_to_file = _detect_static_from_litestar(app)
    assert dir_to_file == "index.html"


def test_detect_static_skips_multi_directory(tmp_path: Path) -> None:
    d1 = tmp_path / "a"
    d2 = tmp_path / "b"
    d1.mkdir()
    d2.mkdir()
    app = Litestar(
        static_files_config=[
            StaticFilesConfig(path="/multi", directories=[str(d1), str(d2)]),
        ]
    )
    routes, mounts, _ = _detect_static_from_litestar(app)
    assert routes == []
    assert mounts == []


def test_detect_static_mixed_eligible_and_skipped(tmp_path: Path) -> None:
    ok = tmp_path / "ok"
    skip = tmp_path / "skip"
    skip2 = tmp_path / "skip2"
    for d in (ok, skip, skip2):
        d.mkdir()
    app = Litestar(
        static_files_config=[
            StaticFilesConfig(path="/ok", directories=[str(ok)]),
            StaticFilesConfig(path="/skip", directories=[str(skip), str(skip2)]),
        ]
    )
    routes, mounts, _ = _detect_static_from_litestar(app)
    assert routes == ["/ok"]
    assert [p.name for p in mounts] == ["ok"]


def test_has_prometheus_plugin_false_when_not_installed() -> None:
    app = Litestar()
    assert _has_prometheus_plugin(app) is False


def test_has_prometheus_plugin_true_when_installed() -> None:
    prometheus = pytest.importorskip("litestar.plugins.prometheus")
    app = Litestar(plugins=[prometheus.PrometheusPlugin()])
    assert _has_prometheus_plugin(app) is True
