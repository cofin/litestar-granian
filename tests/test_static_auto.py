from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from litestar_granian.static import _resolve_static_mounts


class _StaticPlacement(str, Enum):
    """Mirror the provider's str-Enum discriminator so ``==`` comparison is exercised."""

    NATIVE = "native"
    ASGI = "asgi"


class Provider:
    def __init__(self, config: Any) -> None:
        self.config = config

    def get_static_server_config(self) -> Any:
        return self.config


def _mount(directory: Path, route: str = "/assets", directory_index: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(route=route, directory=directory, directory_index=directory_index)


def _config(*mounts: Any, fallback_reason: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(mounts=mounts, fallback_reason=fallback_reason)


def _placement_config(placement: Any, *mounts: Any, reason: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(placement=placement, mounts=mounts, reason=reason)


def _app(*plugins: Any) -> SimpleNamespace:
    return SimpleNamespace(plugins=plugins)


def test_valid_structural_provider_is_selected(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("ok")

    selection = _resolve_static_mounts(_app(Provider(_config(_mount(assets)))), static_mode="auto")

    assert selection is not None
    assert selection.routes == ("/assets",)
    assert selection.mounts == (assets,)
    assert selection.directory_index is None


def test_explicit_mounts_bypass_provider_discovery(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    provider = MagicMock()
    provider.get_static_server_config.side_effect = AssertionError("provider must not be called")

    selection = _resolve_static_mounts(
        _app(provider),
        static_mode="auto",
        explicit_routes=("/manual",),
        explicit_mounts=(assets,),
        explicit_directory_index="index.html",
    )

    assert selection is not None
    assert selection.routes == ("/manual",)
    provider.get_static_server_config.assert_not_called()


@pytest.mark.parametrize(
    "plugins",
    [
        (),
        (Provider(_config()), Provider(_config())),
    ],
)
def test_missing_or_multiple_providers_fall_back_once(
    plugins: tuple[Any, ...],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="litestar_granian.static"):
        selection = _resolve_static_mounts(_app(*plugins), static_mode="auto")

    assert selection is None
    assert len(caplog.records) == 1


@pytest.mark.parametrize(
    "config_factory",
    [
        lambda directory: _config(_mount(directory), fallback_reason="SSR owns assets"),
        lambda directory: _config(_mount(directory, route="assets")),
        lambda directory: _config(_mount(directory.parent / "missing")),
        lambda directory: _config(_mount(directory.parent / "empty")),
        lambda directory: _config(
            _mount(directory, route="/a", directory_index="index.html"),
            _mount(directory, route="/b", directory_index="home.html"),
        ),
        lambda _directory: SimpleNamespace(mounts="not-a-sequence", fallback_reason=None),
    ],
)
def test_ineligible_provider_falls_back_once(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    config_factory: Any,
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("ok")
    (tmp_path / "empty").mkdir()

    with caplog.at_level(logging.INFO, logger="litestar_granian.static"):
        selection = _resolve_static_mounts(
            _app(Provider(config_factory(assets))),
            static_mode="auto",
        )

    assert selection is None
    assert len(caplog.records) == 1


def test_placement_native_is_selected(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("ok")

    config = _placement_config(_StaticPlacement.NATIVE, _mount(assets))
    selection = _resolve_static_mounts(_app(Provider(config)), static_mode="auto")

    assert selection is not None
    assert selection.routes == ("/assets",)
    assert selection.mounts == (assets,)
    assert selection.directory_index is None


def test_placement_asgi_falls_back_with_reason(caplog: pytest.LogCaptureFixture) -> None:
    config = _placement_config(_StaticPlacement.ASGI, reason="SSR owns assets")

    with caplog.at_level(logging.INFO, logger="litestar_granian.static"):
        selection = _resolve_static_mounts(_app(Provider(config)), static_mode="auto")

    assert selection is None
    assert len(caplog.records) == 1
    assert "SSR owns assets" in caplog.text


def test_placement_asgi_without_reason_falls_back_cleanly(caplog: pytest.LogCaptureFixture) -> None:
    config = _placement_config(_StaticPlacement.ASGI, reason=None)

    with caplog.at_level(logging.INFO, logger="litestar_granian.static"):
        selection = _resolve_static_mounts(_app(Provider(config)), static_mode="auto")

    assert selection is None
    assert len(caplog.records) == 1


def test_unknown_placement_falls_back(caplog: pytest.LogCaptureFixture) -> None:
    config = _placement_config("sidecar", reason=None)

    with caplog.at_level(logging.INFO, logger="litestar_granian.static"):
        selection = _resolve_static_mounts(_app(Provider(config)), static_mode="auto")

    assert selection is None
    assert len(caplog.records) == 1
    assert "sidecar" in caplog.text


def test_legacy_config_without_placement_selects_native(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("ok")

    config = _config(_mount(assets))
    assert not hasattr(config, "placement")

    selection = _resolve_static_mounts(_app(Provider(config)), static_mode="auto")

    assert selection is not None
    assert selection.mounts == (assets,)


def test_legacy_fallback_reason_still_honored(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("ok")

    config = _config(_mount(assets), fallback_reason="legacy owns assets")

    with caplog.at_level(logging.INFO, logger="litestar_granian.static"):
        selection = _resolve_static_mounts(_app(Provider(config)), static_mode="auto")

    assert selection is None
    assert len(caplog.records) == 1
    assert "legacy owns assets" in caplog.text
