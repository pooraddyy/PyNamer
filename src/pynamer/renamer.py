from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Optional

from .attributes import AttributeAnalysis
from .config import RenameConfig
from .names import NameFactory
from .symbols import Binding, ClassInfo, FunctionInfo, Scope, ScopeKind, SymbolTable
from .utils import BUILTIN_NAMES, is_renamable


@dataclass
class RenamePlan:
    attribute_map: dict[str, str] = field(default_factory=dict)
    builtin_aliases: dict[str, str] = field(default_factory=dict)
    symbol_map: dict[str, str] = field(default_factory=dict)


class Renamer:
    def __init__(
        self,
        table: SymbolTable,
        attributes: AttributeAnalysis,
        config: RenameConfig,
        factory: NameFactory,
        renaming_map=None,
    ) -> None:
        self.table = table
        self.attributes = attributes
        self.config = config
        self.factory = factory
        self.renaming_map = renaming_map
        self.plan = RenamePlan()
        self._protected_kwargs: set[str] = set()

    def run(self, tree: ast.Module) -> ast.Module:
        self._plan_attributes()
        self._protected_kwargs = self._protected_keyword_params()
        self._plan_bindings()
        rewriter = _Rewriter(self)
        tree = rewriter.visit(tree)
        if self.plan.builtin_aliases:
            _insert_builtin_header(tree, self.plan.builtin_aliases)
        ast.fix_missing_locations(tree)
        return tree

    def _plan_attributes(self) -> None:
        if not self.config.rename_attributes:
            return
        for name in sorted(self.attributes.internal):
            if name in self.config.preserve_attributes:
                continue
            new_name = None
            if self.renaming_map is not None:
                new_name = self.renaming_map.attributes.get(name)
            if new_name is None:
                new_name = self.factory.fresh(name)
                if self.renaming_map is not None:
                    self.renaming_map.attributes[name] = new_name
            else:
                self.factory.reserve(new_name)
            self.plan.attribute_map[name] = new_name

    def _plan_bindings(self) -> None:
        for scope in self.table.scopes():
            frozen = bool(
                scope.func_info is not None
                and getattr(scope.func_info.node, "_pynamer_freeze_params", False)
            )
            for name, binding in scope.names.items():
                if scope.kind is ScopeKind.CLASS:
                    if name in self.plan.attribute_map:
                        binding.new_name = self.plan.attribute_map[name]
                    continue
                if frozen and binding.kind == "param":
                    continue
                if binding.kind == "param" and name in self._protected_kwargs:
                    continue
                if self._renamable_local(binding, scope):
                    binding.new_name = self._symbol_name(name, scope)
        for scope in self.table.scopes():
            for name, binding in scope.names.items():
                if binding.renamed:
                    self.plan.symbol_map.setdefault(name, binding.final)
        self.plan.symbol_map.update(
            {k: v for k, v in self.plan.attribute_map.items() if k != v}
        )

    def _symbol_name(self, name: str, scope: Scope) -> str:
        if self.renaming_map is not None and scope.kind is ScopeKind.MODULE:
            existing = self.renaming_map.symbols.get(name)
            if existing is not None:
                self.factory.reserve(existing)
                return existing
            new = self.factory.fresh(name)
            self.renaming_map.symbols[name] = new
            return new
        return self.factory.fresh(name)

    def _protected_keyword_params(self) -> set[str]:
        protected: set[str] = set()
        blanket = False
        for node in ast.walk(self.table.tree):
            if not isinstance(node, ast.Call):
                continue
            explicit = [kw.arg for kw in node.keywords if kw.arg is not None]
            star = any(kw.arg is None for kw in node.keywords)
            if not explicit and not star:
                continue
            callee = resolve_callee(self.table, node)
            if callee is None:
                protected.update(explicit)
                blanket = blanket or star
            elif star:
                protected.update(callee.params)
        if blanket:
            for scope in self.table.scopes():
                for name, binding in scope.names.items():
                    if binding.kind == "param":
                        protected.add(name)
        return protected

    def _renamable_local(self, binding: Binding, scope: Scope) -> bool:
        name = binding.name
        if binding.kind in ("dotted_import", "typeparam"):
            return False
        node = binding.node
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            return False
        if not is_renamable(name, keep_visit=self.config.preserve_visit_methods):
            return False
        if name in self.config.preserve:
            return False
        if (
            self.config.preserve_public
            and scope.kind is ScopeKind.MODULE
            and not name.startswith("_")
        ):
            return False
        return True

    def _builtin_alias(self, name: str) -> str:
        alias = self.plan.builtin_aliases.get(name)
        if alias is None:
            alias = self.factory.fresh(name)
            self.plan.builtin_aliases[name] = alias
        return alias


class _Rewriter(ast.NodeTransformer):
    def __init__(self, renamer: Renamer) -> None:
        self.renamer = renamer
        self.table = renamer.table
        self.config = renamer.config
        self.attribute_map = renamer.plan.attribute_map

    def _scope(self, node: ast.AST) -> Optional[Scope]:
        return self.table.scope_of(node)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        scope = self._scope(node)
        if scope is None:
            return node
        if isinstance(node.ctx, ast.Load):
            binding = self.table.resolve_load(scope, node.id)
            if binding is not None:
                if binding.renamed:
                    node.id = binding.final
            elif self._should_remap_builtin(node.id):
                node.id = self.renamer._builtin_alias(node.id)
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            binding = self.table.resolve_store(scope, node.id)
            if binding is not None and binding.renamed:
                node.id = binding.final
        return node

    def _should_remap_builtin(self, name: str) -> bool:
        if not self.config.builtins:
            return False
        if name in self.config.preserve:
            return False
        if name not in BUILTIN_NAMES:
            return False
        return is_renamable(name, keep_visit=self.config.preserve_visit_methods)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        self.generic_visit(node)
        scope = self._scope(node)
        if scope is not None:
            binding = scope.names.get(node.arg)
            if binding is not None and binding.renamed:
                node.arg = binding.final
        return node

    def _rename_definition(self, node) -> None:
        scope = self._scope(node)
        if scope is None:
            return
        binding = scope.names.get(node.name)
        if binding is not None and binding.renamed:
            node.name = binding.final

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self._rename_definition(node)
        self.generic_visit(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self._rename_definition(node)
        self._rename_slots(node)
        self.generic_visit(node)
        return node

    def _rename_slots(self, node: ast.ClassDef) -> None:
        for stmt in node.body:
            target_name = None
            value = None
            if isinstance(stmt, ast.Assign):
                value = stmt.value
                if any(
                    isinstance(t, ast.Name) and t.id == "__slots__"
                    for t in stmt.targets
                ):
                    target_name = "__slots__"
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                if stmt.target.id == "__slots__":
                    target_name = "__slots__"
                    value = stmt.value
            if target_name and value is not None:
                self._rename_slot_value(value)

    def _rename_slot_value(self, value: ast.AST) -> None:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            value.value = self.attribute_map.get(value.value, value.value)
        elif isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            for elt in value.elts:
                self._rename_slot_value(elt)

    def visit_Import(self, node: ast.Import) -> ast.AST:
        scope = self._scope(node)
        for alias in node.names:
            if alias.asname:
                bound = alias.asname
                binding = self.table.resolve_store(scope, bound)
                if binding is not None and binding.renamed:
                    alias.asname = binding.final
            elif "." not in alias.name:
                binding = self.table.resolve_store(scope, alias.name)
                if binding is not None and binding.renamed:
                    alias.asname = binding.final
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        scope = self._scope(node)
        for alias in node.names:
            if alias.name == "*":
                continue
            bound = alias.asname or alias.name
            binding = self.table.resolve_store(scope, bound)
            if binding is not None and binding.renamed:
                alias.asname = binding.final
        return node

    def visit_Global(self, node: ast.Global) -> ast.AST:
        self._rewrite_declarations(node)
        return node

    visit_Nonlocal = visit_Global

    def _rewrite_declarations(self, node) -> None:
        scope = self._scope(node)
        if scope is None:
            return
        node.names = [
            binding.final
            if (binding := self.table.resolve_load(scope, name)) is not None
            and binding.renamed
            else name
            for name in node.names
        ]

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        mapped = self.attribute_map.get(node.attr)
        if mapped is not None:
            node.attr = mapped
        return node

    def visit_MatchClass(self, node: ast.MatchClass) -> ast.AST:
        self.generic_visit(node)
        node.kwd_attrs = [self.attribute_map.get(a, a) for a in node.kwd_attrs]
        return node

    def visit_MatchAs(self, node: ast.MatchAs) -> ast.AST:
        self.generic_visit(node)
        if node.name:
            node.name = self._rename_bound(node, node.name)
        return node

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node: ast.MatchMapping) -> ast.AST:
        self.generic_visit(node)
        if node.rest:
            node.rest = self._rename_bound(node, node.rest)
        return node

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.AST:
        self.generic_visit(node)
        if node.name:
            node.name = self._rename_bound(node, node.name)
        return node

    def _rename_bound(self, node: ast.AST, name: str) -> str:
        scope = self._scope(node)
        binding = self.table.resolve_store(scope, name)
        if binding is not None and binding.renamed:
            return binding.final
        return name

    def visit_Call(self, node: ast.Call) -> ast.AST:
        info = None
        string_attr_index = _STRING_ATTR_FUNCS.get(_func_name(node.func))
        if self.config.rename_kwargs and node.keywords:
            info = resolve_callee(self.table, node)
        self.generic_visit(node)
        if string_attr_index is not None:
            self._remap_string_attribute(node, string_attr_index)
        if info is not None:
            param_map = info.param_map()
            if param_map:
                for kw in node.keywords:
                    if kw.arg and kw.arg in param_map:
                        kw.arg = param_map[kw.arg]
        return node

    def _remap_string_attribute(self, node: ast.Call, index: int) -> None:
        if len(node.args) <= index:
            return
        arg = node.args[index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            arg.value = self.attribute_map.get(arg.value, arg.value)


def resolve_callee(table: SymbolTable, node: ast.Call) -> Optional[FunctionInfo]:
    func = node.func
    scope = table.scope_of(node)
    if isinstance(func, ast.Name):
        binding = table.resolve_load(scope, func.id)
        if binding is None:
            return None
        if isinstance(binding.node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return table.functions.get(id(binding.node))
        if isinstance(binding.node, ast.ClassDef):
            info = table.classes.get(id(binding.node))
            return info.lookup_method("__init__") if info else None
        return None
    if isinstance(func, ast.Attribute):
        base = super_base(table, func.value, scope)
        if base is not None:
            for cls in base.mro()[1:]:
                fn = cls.methods.get(func.attr)
                if fn is not None:
                    return fn
            return None
        owner = class_of_value(table, func.value, scope)
        if owner is None:
            return None
        return owner.lookup_method(func.attr)
    return None


def super_base(
    table: SymbolTable, value: ast.AST, scope: Optional[Scope]
) -> Optional[ClassInfo]:
    if not isinstance(value, ast.Call) or not _is_super_call(value):
        return None
    if value.args:
        explicit = table.class_of_expr(value.args[0], scope)
        if explicit is not None:
            return explicit
    return table.enclosing_class(scope)


def class_of_value(
    table: SymbolTable, value: ast.AST, scope: Optional[Scope]
) -> Optional[ClassInfo]:
    if isinstance(value, ast.Name):
        info = table.enclosing_class(scope)
        if info is not None and value.id in info.self_params:
            return info
        return table.class_of_expr(value, scope)
    if isinstance(value, ast.Call):
        if _is_super_call(value):
            return table.enclosing_class(scope)
        return table.class_of_expr(value.func, scope)
    return None


def _is_super_call(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Name) and node.func.id == "super"


def _func_name(func: ast.AST) -> Optional[str]:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


_STRING_ATTR_FUNCS = {"getattr": 1, "setattr": 1, "hasattr": 1, "delattr": 1}


def _insert_builtin_header(tree: ast.Module, aliases: dict[str, str]) -> None:
    items = list(aliases.items())
    targets = [ast.Name(id=alias, ctx=ast.Store()) for _, alias in items]
    values = [ast.Name(id=orig, ctx=ast.Load()) for orig, _ in items]
    if len(items) == 1:
        statement = ast.Assign(targets=[targets[0]], value=values[0])
    else:
        statement = ast.Assign(
            targets=[ast.Tuple(elts=targets, ctx=ast.Store())],
            value=ast.Tuple(elts=values, ctx=ast.Load()),
        )
    ast.fix_missing_locations(statement)
    index = _header_index(tree)
    tree.body.insert(index, statement)


def _header_index(tree: ast.Module) -> int:
    index = 0
    if tree.body and _is_docstring(tree.body[0]):
        index = 1
    while index < len(tree.body) and _is_future_import(tree.body[index]):
        index += 1
    return index


def _is_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_future_import(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__"
