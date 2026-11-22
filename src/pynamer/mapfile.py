from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["RenameMap"]


@dataclass
class RenameMap:

    strategy: str = "sequential"
    seed: int = 0
    prefix: str = "_0x"
    module: str | None = None
    symbols: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "strategy": self.strategy,
            "seed": self.seed,
            "prefix": self.prefix,
            "module": self.module,
            "symbols": dict(sorted(self.symbols.items())),
            "attributes": dict(sorted(self.attributes.items())),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RenameMap":
        return cls(
            strategy=data.get("strategy", "sequential"),
            seed=int(data.get("seed", 0)),
            prefix=data.get("prefix", "_0x"),
            module=data.get("module"),
            symbols=dict(data.get("symbols", {})),
            attributes=dict(data.get("attributes", {})),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> "RenameMap":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def merge(self, other: "RenameMap") -> "RenameMap":
        merged = RenameMap(
            strategy=self.strategy,
            seed=self.seed,
            prefix=self.prefix,
            module=self.module,
        )
        merged.symbols = {**self.symbols, **other.symbols}
        merged.attributes = {**self.attributes, **other.attributes}
        return merged

    def lookup_symbol(self, name: str) -> str:
        return self.symbols.get(name, name)

    def lookup_attribute(self, name: str) -> str:
        return self.attributes.get(name, name)

    def reverse_symbols(self) -> dict[str, str]:
        return {value: key for key, value in self.symbols.items()}

    def reverse_attributes(self) -> dict[str, str]:
        return {value: key for key, value in self.attributes.items()}

    def __bool__(self) -> bool:
        return True

    def __len__(self) -> int:
        return len(self.symbols) + len(self.attributes)
