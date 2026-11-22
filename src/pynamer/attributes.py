from __future__ import annotations

import ast
from dataclasses import dataclass, field

from .symbols import ClassInfo, ScopeKind, SymbolTable
from .utils import attr_is_renamable, target_names


@dataclass
class AttributeAnalysis:
    internal: set[str] = field(default_factory=set)
    external: set[str] = field(default_factory=set)
    instance_attrs: dict[int, set[str]] = field(default_factory=dict)
    instance_vars: set[str] = field(default_factory=set)


class AttributeAnalyzer:
    def __init__(self, table: SymbolTable, *, track_instances: bool = False) -> None:
        self.table = table
        self.tree = table.tree
        self.track_instances = track_instances
        self.result = AttributeAnalysis()
        self._external: set[str] = set()
        self._defined: set[str] = set()

    def run(self) -> AttributeAnalysis:
        if self.track_instances:
            self.result.instance_vars = self._collect_instance_vars()
        self._collect_defined_attributes()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute):
                self._classify(node)
        self.result.external = self._external
        self.result.internal = {
            name
            for name in self._defined
            if attr_is_renamable(name) and name not in self._external
        }
        return self.result

    def _collect_defined_attributes(self) -> None:
        for info in self.table.classes.values():
            for name, binding in info.scope.names.items():
                if binding.kind == "typeparam":
                    continue
                if attr_is_renamable(name):
                    self._defined.add(name)
            self.result.instance_attrs[id(info)] = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute) and isinstance(
                node.ctx, (ast.Store, ast.Del)
            ):
                owner = self._self_owner(node)
                if owner is not None:
                    self.result.instance_attrs.setdefault(id(owner), set()).add(
                        node.attr
                    )
                    if attr_is_renamable(node.attr):
                        self._defined.add(node.attr)

    def _self_owner(self, node: ast.Attribute) -> ClassInfo | None:
        base = node.value
        if not isinstance(base, ast.Name):
            return None
        scope = self.table.scope_of(node)
        info = self.table.enclosing_class(scope)
        if info is not None and base.id in info.self_params:
            return info
        return None

    def _classify(self, node: ast.Attribute) -> None:
        if self._is_internal_base(node):
            return
        self._external.add(node.attr)

    def _is_internal_base(self, node: ast.Attribute) -> bool:
        base = node.value
        scope = self.table.scope_of(node)

        if isinstance(base, ast.Name):
            info = self.table.enclosing_class(scope)
            if info is not None and base.id in info.self_params:
                return True
            if self.table.class_of_expr(base, scope) is not None:
                return True
            if base.id in self.result.instance_vars:
                return True
            return False

        if isinstance(base, ast.Call):
            if self._is_super_call(base):
                info = self.table.enclosing_class(scope)
                if info is None:
                    return False
                return any(
                    node.attr in cls.methods or node.attr in cls.local_attrs()
                    for cls in info.mro()[1:]
                )
            if self.table.class_of_expr(base.func, scope) is not None:
                return True
            return False

        return False

    @staticmethod
    def _is_super_call(node: ast.Call) -> bool:
        return isinstance(node.func, ast.Name) and node.func.id == "super"

    def _collect_instance_vars(self) -> set[str]:
        candidates: set[str] = set()
        disqualified: set[str] = set()

        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                names = self._assign_targets(node.targets)
                if self._is_local_ctor(node.value, node):
                    candidates |= names
                else:
                    disqualified |= names
            elif isinstance(node, ast.AnnAssign):
                ok = self._is_local_ctor(node.value, node)
                if not ok:
                    ok = isinstance(node.annotation, ast.Name) and (
                        self.table.class_of_expr(node.annotation, self._scope(node))
                        is not None
                    )
                (candidates if ok else disqualified).update(
                    target_names(node.target)
                )
            elif isinstance(node, (ast.AugAssign, ast.For, ast.AsyncFor)):
                disqualified |= target_names(node.target)
            elif isinstance(node, ast.comprehension):
                disqualified |= target_names(node.target)
            elif isinstance(node, ast.NamedExpr):
                disqualified |= target_names(node.target)
            elif isinstance(node, ast.withitem) and node.optional_vars is not None:
                disqualified |= target_names(node.optional_vars)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                disqualified.add(node.name)
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
            ):
                for arg in (
                    list(node.args.posonlyargs)
                    + list(node.args.args)
                    + list(node.args.kwonlyargs)
                ):
                    disqualified.add(arg.arg)
                if node.args.vararg:
                    disqualified.add(node.args.vararg.arg)
                if node.args.kwarg:
                    disqualified.add(node.args.kwarg.arg)

        return candidates - disqualified

    def _scope(self, node: ast.AST):
        return self.table.scope_of(node)

    def _is_local_ctor(self, value: ast.AST | None, ctx: ast.AST) -> bool:
        if not isinstance(value, ast.Call):
            return False
        return self.table.class_of_expr(value.func, self._scope(ctx)) is not None

    @staticmethod
    def _assign_targets(targets: list[ast.AST]) -> set[str]:
        names: set[str] = set()
        for target in targets:
            names |= target_names(target)
        return names
