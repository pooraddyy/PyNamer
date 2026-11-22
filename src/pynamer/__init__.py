from __future__ import annotations

from .api import RenameResult, RenameStats, process, rename, rename_ast
from .api import collect_identifiers
from .config import NameStrategy, RenameConfig
from .errors import (
    AnalysisError,
    ConfigurationError,
    PynamerError,
    TransformError,
    ValidationError,
)
from .mapfile import RenameMap
from .minify import minify_source

__version__ = "0.2.1"

__all__ = [
    "__version__",
    "process",
    "rename",
    "rename_ast",
    "collect_identifiers",
    "minify_source",
    "RenameConfig",
    "NameStrategy",
    "RenameMap",
    "RenameResult",
    "RenameStats",
    "PynamerError",
    "ConfigurationError",
    "AnalysisError",
    "TransformError",
    "ValidationError",
]
