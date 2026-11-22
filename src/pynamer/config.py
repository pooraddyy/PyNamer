from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterable

from .errors import ConfigurationError

if TYPE_CHECKING:
    from .mapfile import RenameMap


class NameStrategy(str, Enum):

    SEQUENTIAL = "sequential"
    HASH = "hash"
    RANDOM = "random"
    BASE62 = "base62"
    WORDS = "words"


def _as_frozenset(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, (str, bytes)):
        raise ConfigurationError("preserve sets must be iterables of names, not a string")
    return frozenset(str(item) for item in value)


@dataclass(frozen=True)
class RenameConfig:

    strategy: NameStrategy = NameStrategy.SEQUENTIAL
    seed: int = 0
    prefix: str = "_0x"

    minify: bool = True
    strip_docstrings: bool = False

    builtins: bool = False
    hide_init: bool = False
    track_instances: bool = False

    hide_strings: bool = True
    hide_imports: bool = True

    rename_attributes: bool = True
    rename_kwargs: bool = True

    preserve: frozenset[str] = field(default_factory=frozenset)
    preserve_attributes: frozenset[str] = field(default_factory=frozenset)
    preserve_public: bool = False
    preserve_visit_methods: bool = True
    validate: bool = True

    map: "RenameMap | None" = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "preserve", _as_frozenset(self.preserve))
        object.__setattr__(
            self, "preserve_attributes", _as_frozenset(self.preserve_attributes)
        )
        if not isinstance(self.strategy, NameStrategy):
            try:
                object.__setattr__(self, "strategy", NameStrategy(self.strategy))
            except ValueError as exc:
                raise ConfigurationError(f"unknown strategy {self.strategy!r}") from exc
        if self.prefix and not _valid_prefix(self.prefix):
            raise ConfigurationError(
                f"prefix {self.prefix!r} cannot start a Python identifier"
            )

    def merged(self, **overrides: Any) -> "RenameConfig":
        clean = {k: v for k, v in overrides.items() if v is not None}
        if not clean:
            return self
        unknown = set(clean) - set(self.__dataclass_fields__)
        if unknown:
            raise ConfigurationError(
                "unknown configuration option(s): " + ", ".join(sorted(unknown))
            )
        clean["preserve"] = _as_frozenset(clean.get("preserve", self.preserve))
        clean["preserve_attributes"] = _as_frozenset(
            clean.get("preserve_attributes", self.preserve_attributes)
        )
        return replace(self, **clean)


def _valid_prefix(prefix: str) -> bool:
    first = prefix[0]
    return first == "_" or first.isalpha()
