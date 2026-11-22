from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field
from typing import Any, Iterator, Union

from .attributes import AttributeAnalyzer
from .config import NameStrategy, RenameConfig
from .errors import AnalysisError, ValidationError
from .mapfile import RenameMap
from .minify import minify_source
from .names import NameFactory
from .renamer import Renamer
from .symbols import SymbolTable
from .transforms import (
    apply_hide_init,
    hide_imports,
    hide_strings,
    strip_docstrings,
)
from .utils import BUILTIN_NAMES, HARD_RESERVED

__all__ = [
    "process",
    "rename",
    "rename_ast",
    "collect_identifiers",
    "RenameResult",
    "RenameStats",
]

Source = Union[str, ast.Module]


@dataclass
class RenameStats:

    symbols: int = 0
    attributes: int = 0
    builtins: int = 0
    input_size: int = 0
    output_size: int = 0

    @property
    def saved(self) -> int:
        return max(0, self.input_size - self.output_size)

    def as_dict(self) -> dict:
        return {
            "symbols": self.symbols,
            "attributes": self.attributes,
            "builtins": self.builtins,
            "input_size": self.input_size,
            "output_size": self.output_size,
            "saved": self.saved,
        }


@dataclass
class RenameResult:

    source: str
    tree: ast.Module
    mapping: RenameMap
    config: RenameConfig
    stats: RenameStats
    plan: Any = field(default=None, repr=False)

    export = None

    def __repr__(self) -> str:
        return (
            f"RenameResult(symbols={self.stats.symbols}, "
            f"attributes={self.stats.attributes}, "
            f"size={self.stats.input_size}->{self.stats.output_size})"
        )


def process(
    source: Source,
    *,
    filename: str = "<pynamer>",
    config: RenameConfig | None = None,
    **overrides: Any,
) -> RenameResult:
    cfg = _resolve_config(config, overrides)
    if isinstance(source, str):
        text = source
        try:
            tree = ast.parse(text, filename=filename)
        except SyntaxError as exc:
            raise AnalysisError(f"failed to parse {filename}: {exc}") from exc
    elif isinstance(source, ast.Module):
        text = ""
        tree = copy.deepcopy(source)
    else:
        raise TypeError(
            f"source must be str or ast.Module, got {type(source).__name__}"
        )
    return _transform(tree, text, filename, cfg)


def rename(source: Source, **kwargs: Any) -> str:
    return process(source, **kwargs).source


def rename_ast(source: Source, **kwargs: Any) -> ast.Module:
    return process(source, **kwargs).tree


def _resolve_config(
    config: RenameConfig | None, overrides: dict[str, Any]
) -> RenameConfig:
    base = config if config is not None else RenameConfig()
    if not isinstance(base, RenameConfig):
        raise TypeError("config must be a RenameConfig instance")
    clean = {k: v for k, v in overrides.items() if v is not None}
    return base.merged(**clean) if clean else base


def _blank_map(cfg: RenameConfig) -> RenameMap:
    return RenameMap(
        strategy=NameStrategy(cfg.strategy).value,
        seed=cfg.seed,
        prefix=cfg.prefix,
    )


def _transform(
    tree: ast.Module, text: str, filename: str, cfg: RenameConfig
) -> RenameResult:
    if cfg.strip_docstrings:
        strip_docstrings(tree)
    if cfg.hide_init:
        apply_hide_init(tree)
    ast.fix_missing_locations(tree)

    table = SymbolTable(tree)
    attributes = AttributeAnalyzer(table, track_instances=cfg.track_instances).run()

    renaming_map = cfg.map if cfg.map is not None else _blank_map(cfg)
    reserved = set(HARD_RESERVED) | set(BUILTIN_NAMES) | collect_identifiers(tree)
    factory = NameFactory(
        strategy=cfg.strategy,
        seed=cfg.seed,
        prefix=cfg.prefix,
        reserved=reserved,
    )

    renamer = Renamer(table, attributes, cfg, factory, renaming_map=renaming_map)
    tree = renamer.run(tree)

    if cfg.hide_imports:
        tree = hide_imports(tree)
    if cfg.hide_strings:
        tree = hide_strings(tree, seed=cfg.seed, prefix=cfg.prefix)
    ast.fix_missing_locations(tree)

    out = ast.unparse(tree)
    out = minify_source(out) if cfg.minify else out.rstrip() + "\n"

    if cfg.validate:
        try:
            compile(out, filename, "exec")
        except (SyntaxError, ValueError) as exc:
            raise ValidationError(
                f"obfuscated source did not compile: {exc}", source=out
            ) from exc

    stats = RenameStats(
        symbols=sum(1 for k, v in renaming_map.symbols.items() if k != v),
        attributes=sum(1 for k, v in renaming_map.attributes.items() if k != v),
        builtins=len(renamer.plan.builtin_aliases),
        input_size=len(text),
        output_size=len(out),
    )
    result = RenameResult(out, tree, renaming_map, cfg, stats, plan=renamer.plan)
    result.export = lambda path: renaming_map.save(path)
    return result


def collect_identifiers(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in _iter_nodes(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split(".")[0])
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            names.add(node.rest)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        else:
            tp_name = getattr(node, "name", None)
            if isinstance(tp_name, str) and type(node).__name__.endswith(
                ("TypeVar", "ParamSpec", "TypeVarTuple")
            ):
                names.add(tp_name)
    return names


def _iter_nodes(tree: ast.AST) -> Iterator[ast.AST]:
    yield from ast.walk(tree)
