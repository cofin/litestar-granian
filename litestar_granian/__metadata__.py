"""Metadata for the Project."""
from __future__ import annotations

import importlib.metadata

__all__ = ["__version__", "__project__"]

__version__ = importlib.metadata.version("asyncpg_litestar")
"""Version of the project."""
__project__ = importlib.metadata.metadata("asyncpg_litestar")["Name"]
"""Name of the project."""
