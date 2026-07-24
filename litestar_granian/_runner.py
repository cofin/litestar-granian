"""Run Granian with Litestar reload and inherited-socket compatibility."""

import inspect
import json
import os
import socket
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from watchfiles.filters import DefaultFilter

if TYPE_CHECKING:
    from collections.abc import Callable


class _ReloadPatternFilter(DefaultFilter):
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


def _granian_version() -> str:
    try:
        return version("granian")
    except PackageNotFoundError:
        return "unknown"


if sys.platform == "win32":
    _SOCKET_HOLDER_PARAMETERS: tuple[str, ...] = ("fd",)
elif sys.platform == "linux" or sys.platform.startswith("freebsd"):
    _SOCKET_HOLDER_PARAMETERS = ("fd", "uds", "backlog")
else:
    _SOCKET_HOLDER_PARAMETERS = ("fd", "uds")


def _accepts_socket_holder_arguments(candidate: Any) -> bool:
    """Check the candidate against this platform's SocketHolder constructor.

    Granian compiles a different ``SocketHolder`` constructor per platform,
    and native extension classes do not expose a signature on every build,
    so an unavailable signature is treated as compatible.

    Returns:
        Whether the platform's positional arguments are accepted as far as
        the available signature information can prove.
    """
    try:
        signature = inspect.signature(candidate)
    except (TypeError, ValueError):
        return True
    try:
        signature.bind(*range(len(_SOCKET_HOLDER_PARAMETERS)))
    except TypeError:
        return False
    return True


def _probe_granian_compatibility(granian_cli: Any) -> None:
    """Verify the private Granian internals this module patches still exist.

    Raises:
        SystemExit: If the installed Granian release no longer exposes the entry
            points, server hook, or socket constructor this module depends on.
    """
    problems: list[str] = []

    if not callable(getattr(granian_cli, "entrypoint", None)):
        problems.append("granian.cli.entrypoint is missing")

    server_cls = getattr(granian_cli, "Server", None)
    if not isinstance(server_cls, type):
        problems.append("granian.cli.Server is missing")
    elif not callable(getattr(server_cls, "_init_shared_socket", None)):
        problems.append(f"{server_cls.__name__}._init_shared_socket is missing")

    try:
        from granian._granian import SocketHolder
    except ImportError:
        problems.append("granian._granian.SocketHolder is missing")
    else:
        if not _accepts_socket_holder_arguments(SocketHolder):
            problems.append(f"granian._granian.SocketHolder no longer accepts ({', '.join(_SOCKET_HOLDER_PARAMETERS)})")

    if problems:
        message = (
            "litestar-granian's Granian compatibility shim does not match installed "
            f"granian {_granian_version()}: {'; '.join(problems)}. "
            "Pin granian==2.7.* or drop --fd/--reload-include/--reload-exclude."
        )
        raise SystemExit(message)


def _configure_server(granian_cli: Any) -> None:
    from granian._granian import SocketHolder

    includes = _load_patterns("LITESTAR_GRANIAN_RELOAD_INCLUDES")
    excludes = _load_patterns("LITESTAR_GRANIAN_RELOAD_EXCLUDES")
    raw_fd = os.getenv("LITESTAR_GRANIAN_FILE_DESCRIPTOR")
    inherited_fd = int(raw_fd) if raw_fd is not None else None
    original_server = granian_cli.Server
    socket_holder_factory = cast("Callable[..., Any]", SocketHolder)

    class LitestarGranianServer(original_server):  # type: ignore[misc,valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            if includes or excludes:
                reload_filter = type(
                    "LitestarReloadFilter",
                    (_ReloadPatternFilter,),
                    {"include_patterns": includes, "exclude_patterns": excludes},
                )
                kwargs["reload_filter"] = reload_filter
            super().__init__(*args, **kwargs)

        def _init_shared_socket(self) -> None:
            if inherited_fd is None:
                super()._init_shared_socket()
                return
            inherited_socket = socket.socket(fileno=inherited_fd)
            is_uds = inherited_socket.family == getattr(socket, "AF_UNIX", object())
            inherited_socket.detach()
            holder_values = {"fd": inherited_fd, "uds": is_uds, "backlog": self.backlog}
            self._shd = socket_holder_factory(*(holder_values[name] for name in _SOCKET_HOLDER_PARAMETERS))
            self._sfd = self._shd.get_fd()
            self._sso = socket.socket(fileno=self._sfd)
            self._sso.set_inheritable(True)

    setattr(granian_cli, "Server", LitestarGranianServer)


def main() -> None:
    """Run Granian with Litestar CLI compatibility hooks enabled."""
    import granian.cli

    _probe_granian_compatibility(granian.cli)
    _configure_server(granian.cli)

    entrypoint = cast("Callable[[], None]", granian.cli.entrypoint)
    entrypoint()


if __name__ == "__main__":
    main()
