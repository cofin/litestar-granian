"""Resolve explicit or provider-supplied Granian native static mounts."""

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

StaticMode = Literal["off", "auto"]

logger = logging.getLogger("litestar_granian.static")


@dataclass(frozen=True)
class _StaticMounts:
    routes: tuple[str, ...]
    mounts: tuple[Path, ...]
    directory_index: str | None


def _resolve_static_mounts(
    app: Any,
    *,
    static_mode: StaticMode,
    explicit_routes: tuple[str, ...] = (),
    explicit_mounts: tuple[Path, ...] = (),
    explicit_directory_index: str | None = None,
) -> _StaticMounts | None:
    """Resolve explicit mounts or one structural static provider.

    Returns:
        Validated native mounts, or ``None`` when Litestar should serve them.

    Raises:
        ValueError: If explicit route and mount counts differ.
    """
    if explicit_routes or explicit_mounts:
        if len(explicit_routes) != len(explicit_mounts):
            message = "static route and mount counts must match"
            raise ValueError(message)
        return _StaticMounts(
            routes=explicit_routes,
            mounts=tuple(Path(path).resolve() for path in explicit_mounts),
            directory_index=explicit_directory_index,
        )
    if static_mode == "off":
        return None

    providers = [provider for provider in app.plugins if callable(getattr(provider, "get_static_server_config", None))]
    if len(providers) != 1:
        return _fallback(f"expected exactly one static provider, found {len(providers)}")

    try:
        provider_config = providers[0].get_static_server_config()
        return _validate_provider_config(provider_config)
    except Exception as exc:  # ruff: ignore[blind-except]
        return _fallback(str(exc))


def _validate_provider_config(provider_config: Any) -> _StaticMounts | None:
    placement = getattr(provider_config, "placement", None)
    if placement is not None:
        if placement == "asgi":
            reason = getattr(provider_config, "reason", None)
            return _fallback(str(reason) if reason else "static provider selected ASGI placement")
        if placement != "native":
            return _fallback(f"static provider returned unexpected placement: {placement!r}")

    fallback_reason = getattr(provider_config, "fallback_reason", None)
    if fallback_reason:
        return _fallback(str(fallback_reason))

    mounts = getattr(provider_config, "mounts", None)
    if not isinstance(mounts, Sequence) or isinstance(mounts, (str, bytes)) or not mounts:
        message = "static provider returned no usable mounts"
        raise ValueError(message)

    routes: list[str] = []
    directories: list[Path] = []
    directory_indexes: set[str | None] = set()
    for mount in mounts:
        route = getattr(mount, "route", None)
        directory = getattr(mount, "directory", None)
        directory_index = getattr(mount, "directory_index", None)
        if not _is_local_absolute_route(route):
            message = f"static route must be a local absolute path: {route!r}"
            raise ValueError(message)
        route = cast("str", route)
        if directory_index is not None and (
            not isinstance(directory_index, str) or not directory_index or Path(directory_index).name != directory_index
        ):
            message = "static directory index must be a filename"
            raise ValueError(message)
        if not isinstance(directory, (str, os.PathLike)):
            message = "static directory must be a filesystem path"
            raise TypeError(message)
        directory_path = Path(directory).resolve()
        if not directory_path.is_dir() or not _directory_has_entries(directory_path):
            message = f"static directory must exist and be non-empty: {directory_path}"
            raise ValueError(message)
        routes.append(route)
        directories.append(directory_path)
        directory_indexes.add(directory_index)

    if len(directory_indexes) != 1:
        message = "all native static mounts must use the same directory index"
        raise ValueError(message)
    return _StaticMounts(
        routes=tuple(routes),
        mounts=tuple(directories),
        directory_index=directory_indexes.pop(),
    )


def _is_local_absolute_route(route: object) -> bool:
    if not isinstance(route, str) or not route.startswith("/") or route.startswith("//"):
        return False
    parsed = urlsplit(route)
    return not parsed.scheme and not parsed.netloc and not parsed.query and not parsed.fragment


def _directory_has_entries(directory: Path) -> bool:
    with os.scandir(directory) as entries:
        return next(entries, None) is not None


def _fallback(_reason: str) -> _StaticMounts | None:
    logger.info("Using Litestar for static files")
    return None
