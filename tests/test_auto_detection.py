"""Phase 4 — auto-detection helpers."""

from __future__ import annotations

import pytest
from litestar import Litestar

from litestar_granian.cli import _has_prometheus_plugin


def test_has_prometheus_plugin_false_when_not_installed() -> None:
    app = Litestar()
    assert _has_prometheus_plugin(app) is False


def test_has_prometheus_plugin_true_when_installed() -> None:
    prometheus = pytest.importorskip("litestar.plugins.prometheus")
    app = Litestar(plugins=[prometheus.PrometheusPlugin()])
    assert _has_prometheus_plugin(app) is True
