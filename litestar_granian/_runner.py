"""Run Granian with Litestar reload and inherited-socket compatibility."""

import json
import os
import socket
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from watchfiles.filters import DefaultFilter

if TYPE_CHECKING:
    from collections.abc import Callable


class _LitestarReloadFilter(DefaultFilter):
    """Apply Litestar's reload globs to Granian's reloader."""

    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()

    def __init__(
        self,
        includes: tuple[str, ...] | None = None,
        excludes: tuple[str, ...] | None = None,
    ) -> None:
        configured_includes = includes if includes is not None else self.include_patterns
        configured_excludes = excludes if excludes is not None else self.exclude_patterns
        default_includes = () if "*.py" in configured_excludes else ("*.py",)
        self._includes = tuple(dict.fromkeys((*default_includes, *configured_includes)))
        default_excludes = (".*", ".py[cod]", ".sw.*", "~*")
        self._excludes = tuple(
            pattern for pattern in (*default_excludes, *configured_excludes) if pattern not in self._includes
        )
        self._exclude_dirs = tuple(
            path.resolve() for pattern in configured_excludes if (path := Path(pattern)).is_dir()
        )
        super().__init__()

    def __call__(self, change: Any, path: str) -> bool:
        candidate = Path(path)
        if not any(candidate.match(pattern) for pattern in self._includes):
            return False
        if any(directory == candidate or directory in candidate.parents for directory in self._exclude_dirs):
            return False
        if any(candidate.match(pattern) for pattern in self._excludes):
            return False
        return super().__call__(change, path)


def _load_patterns(name: str) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return ()
    values = json.loads(raw)
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        msg = f"{name} must contain a JSON list of strings"
        raise ValueError(msg)
    return tuple(values)


def _configure_server() -> None:
    import granian.cli
    from granian._granian import SocketHolder

    includes = _load_patterns("LITESTAR_GRANIAN_RELOAD_INCLUDES")
    excludes = _load_patterns("LITESTAR_GRANIAN_RELOAD_EXCLUDES")
    raw_fd = os.getenv("LITESTAR_GRANIAN_FILE_DESCRIPTOR")
    inherited_fd = int(raw_fd) if raw_fd is not None else None
    original_server = granian.cli.Server  # type: ignore[attr-defined]
    socket_holder_factory = cast("Callable[[int, bool, int], Any]", SocketHolder)

    class CompatibilityServer(original_server):  # type: ignore[misc,valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if includes or excludes:
                reload_filter = type(
                    "LitestarReloadFilter",
                    (_LitestarReloadFilter,),
                    {"include_patterns": includes, "exclude_patterns": excludes},
                )
                kwargs["reload_filter"] = reload_filter
            super().__init__(*args, **kwargs)

        def _init_shared_socket(self) -> None:
            if inherited_fd is None:
                super()._init_shared_socket()
                return
            inherited_socket = socket.socket(fileno=inherited_fd)
            is_uds = inherited_socket.family == socket.AF_UNIX
            inherited_socket.detach()
            self._shd = socket_holder_factory(inherited_fd, is_uds, self.backlog)
            self._sfd = self._shd.get_fd()
            self._sso = socket.socket(fileno=self._sfd)
            self._sso.set_inheritable(True)

    setattr(granian.cli, "Server", CompatibilityServer)


def main() -> None:
    """Run Granian with Litestar CLI compatibility hooks enabled."""
    _configure_server()
    import granian.cli

    entrypoint = cast("Callable[[], None]", granian.cli.entrypoint)
    entrypoint()


if __name__ == "__main__":
    main()
