"""Metadata for the Project."""

from importlib.metadata import PackageNotFoundError, metadata, version  # pragma: no cover

__all__ = ("__project__", "__version__")  # pragma: no cover

try:  # pragma: no cover
    __version__ = version("litestar_granian")
    """Version of the project."""
    __project__ = metadata("litestar_granian")["Name"]
    """Name of the project."""
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.1"
    __project__ = "Litestar Granian"
finally:  # pragma: no cover
    del version, PackageNotFoundError, metadata
