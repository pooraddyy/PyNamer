from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Optional

from .utils import is_staticmethod


class ScopeKind(str, Enum):
    MODULE = "module"
    FUNCTION = "function"
    LAMBDA = "lambda"
    CLASS = "class"
    COMPREHENSION = "comprehension"


_FUNCTION_SCOPES = (ScopeKind.FUNCTION, ScopeKind.LAMBDA)


@dataclass
class Binding:

    name: str
    kind: str
    node: Optional[ast.AST] = None
    new_name: Optional[str] = None

    @property
    def final(self) -> str:
        return self.new_name or self.name

    @property
    def renamed(self) -> bool:
        return self.new_name is not None and self.new_name != self.name


@dataclass
class FunctionInfo:
    node: ast.AST
    scope: "Scope"
    params: list[str] = field(default_factory=list)
    is_method: bool = False
    is_static: bool = False
    owner: Optional["ClassInfo"] = None

    def param_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in self.params:
            binding = self.scope.names.get(name)
            if binding is not None and binding.renamed:
                out[name] = binding.final
        return out


@dataclass
class ClassInfo:
    node: ast.ClassDef
    scope: "Scope"
    name: str
    binding: Optional[Binding] = None
    bases: list[ast.AST] = field(default_factory=list)
    methods: dict[str, FunctionInfo] = field(default_factory=dict)
    self_params: set[str] = field(default_factory=set)
    instance_attrs: set[str] = field(default_factory=set)
    resolved_bases: list["ClassInfo"] = field(default_factory=list)
    metaclass: Optional[ast.expr] = None
    _mro: Optional[list["ClassInfo"]] = field(default=None, repr=False)

    def local_attrs(self) -> set[str]:
        return set(self.scope.names)

    def mro(self) -> list["ClassInfo"]:
        if self._mro is not None:
            return self._mro
        order: list[ClassInfo] = []
        seen: set[int] = set()

        def walk(cls: ClassInfo) -> None:
            if id(cls) in seen:
                return
            seen.add(id(cls))
            order.append(cls)
            for base in cls.resolved_bases:
                walk(base)

        walk(self)
        self._mro = order
        return order

    def lookup_method(self, name: str) -> Optional[FunctionInfo]:
        for cls in self.mro():
            fn = cls.methods.get(name)
            if fn is not None:
                return fn
        return None


@dataclass
class Scope:
    kind: ScopeKind
    parent: Optional["Scope"] = None
    node: Optional[ast.AST] = None
    module: Optional["Scope"] = None
    names: dict[str, Binding] = field(default_factory=dict)
    children: list["Scope"] = field(default_factory=list)
    globals: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)
    func_info: Optional[FunctionInfo] = None
    class_info: Optional[ClassInfo] = None

    def bind(self, name: str, kind: str, node: Optional[ast.AST] = None) -> Binding:
        binding = self.names.get(name)
        if binding is None:
            binding = Binding(name, kind, node)
            self.names[name] = binding
        elif binding.kind == "typeparam" and kind != "typeparam":
            binding.kind = kind
            if node is not None:
                binding.node = node
        return binding

    def walk(self) -> Iterator["Scope"]:
        yield self
        for child in self.children:
            yield from child.walk()


class ScopeBuilder(ast.NodeVisitor):

    def __init__(self) -> None:
        self.module = Scope(ScopeKind.MODULE)
        self.module.module = self.module
        self._stack: list[Scope] = [self.module]
        self.node_scope: dict[int, Scope] = {}
        self.classes: dict[int, ClassInfo] = {}
        self.functions: dict[int, FunctionInfo] = {}
        self.global_names: set[str] = set()
        self.nonlocal_names: set[str] = set()
        self.type_params: set[str] = set()

    @property
    def current(self) -> Scope:
        return self._stack[-1]

    def visit(self, node):
        if isinstance(node, ast.AST):
            self.node_scope[id(node)] = self.current
        return super().visit(node)

    def _push(self, kind: ScopeKind, node: ast.AST) -> Scope:
        scope = Scope(kind, parent=self.current, node=node, module=self.module)
        self.current.children.append(scope)
        self._stack.append(scope)
        return scope

    def _pop(self) -> Scope:
        return self._stack.pop()

    def _record(self, node: ast.AST, scope: Scope) -> None:
        self.node_scope[id(node)] = scope

    def visit_Module(self, node: ast.Module) -> None:
        node._scope = self.module
        self.module.node = node
        for stmt in node.body:
            self.visit(stmt)

    def _visit_type_params(self, params, target_scope: Scope) -> None:
        for tp in params or ():
            name = getattr(tp, "name", None)
            if name:
                self.type_params.add(name)
                target_scope.bind(name, "typeparam", tp)
            self._record(tp, self._stack[-2])
            bound = getattr(tp, "bound", None)
            if bound is not None:
                self.visit(bound)
            default = getattr(tp, "default_value", None)
            if default is not None:
                self.visit(default)

    def _visit_function_like(
        self,
        node: ast.AST,
        *,
        scope_kind: ScopeKind,
        is_async: bool = False,
    ) -> None:
        args = node.args
        for deco in getattr(node, "decorator_list", []):
            self.visit(deco)
        for default in args.defaults:
            self.visit(default)
        for default in args.kw_defaults:
            if default is not None:
                self.visit(default)
        for arg in (
            list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        ):
            if arg.annotation is not None:
                self.visit(arg.annotation)
        if args.vararg and args.vararg.annotation is not None:
            self.visit(args.vararg.annotation)
        if args.kwarg and args.kwarg.annotation is not None:
            self.visit(args.kwarg.annotation)
        if getattr(node, "returns", None) is not None:
            self.visit(node.returns)

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.current.bind(node.name, "function", node)

        scope = self._push(scope_kind, node)
        node._scope = scope
        self._record(node, self._stack[-2])

        self._visit_type_params(getattr(node, "type_params", None), scope)
        self._bind_arguments(args, scope)

        info = FunctionInfo(
            node=node,
            scope=scope,
            params=_param_order(args),
        )
        scope.func_info = info
        self.functions[id(node)] = info

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            enclosing = self._stack[-2]
            if enclosing.kind is ScopeKind.CLASS and enclosing.class_info is not None:
                owner = enclosing.class_info
                info.is_method = True
                info.is_static = is_staticmethod(node)
                info.owner = owner
                owner.methods[node.name] = info
                if not info.is_static and info.params:
                    owner.self_params.add(info.params[0])

        for stmt in node.body:
            self.visit(stmt)
        self._pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_like(node, scope_kind=ScopeKind.FUNCTION)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_like(node, scope_kind=ScopeKind.FUNCTION, is_async=True)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        scope = self._push(ScopeKind.LAMBDA, node)
        node._scope = scope
        self._bind_arguments(node.args, scope)
        info = FunctionInfo(node=node, scope=scope, params=_param_order(node.args))
        scope.func_info = info
        self.functions[id(node)] = info
        self.visit(node.body)
        self._pop()

    def _bind_arguments(self, args: ast.arguments, scope: Scope) -> None:
        ordered = (
            list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        )
        if args.vararg is not None:
            ordered.append(args.vararg)
        if args.kwarg is not None:
            ordered.append(args.kwarg)
        for arg in ordered:
            scope.bind(arg.arg, "param", arg)
            self._record(arg, scope)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for deco in node.decorator_list:
            self.visit(deco)
        for base in node.bases:
            self.visit(base)
        for kw in node.keywords:
            self.visit(kw.value)

        binding = self.current.bind(node.name, "class", node)
        scope = self._push(ScopeKind.CLASS, node)
        node._scope = scope

        info = ClassInfo(
            node=node,
            scope=scope,
            name=node.name,
            binding=binding,
            bases=list(node.bases),
        )
        scope.class_info = info
        self.classes[id(node)] = info

        self._visit_type_params(getattr(node, "type_params", None), scope)

        for kw in node.keywords:
            if kw.arg == "metaclass":
                info.metaclass = kw.value

        for stmt in node.body:
            self.visit(stmt)
        self._pop()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.current.bind(node.id, "local", node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        target = node.target
        if isinstance(target, ast.Name):
            scope = self._walrus_scope()
            scope.bind(target.id, "local", target)
            self._record(target, scope)
        else:
            self.visit(target)

    def _walrus_scope(self) -> Scope:
        scope = self.current
        while scope.kind is ScopeKind.COMPREHENSION and scope.parent is not None:
            scope = scope.parent
        return scope

    def visit_Global(self, node: ast.Global) -> None:
        self.current.globals.update(node.names)
        self.global_names.update(node.names)
        for name in node.names:
            self.module.bind(name, "global")

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.current.nonlocals.update(node.names)
        self.nonlocal_names.update(node.names)
        scope = self.current.parent
        while scope is not None and scope.kind not in _FUNCTION_SCOPES:
            scope = scope.parent
        if scope is not None:
            for name in node.names:
                scope.bind(name, "local")

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self.current.bind(node.name, "local", node)
        for stmt in node.body:
            self.visit(stmt)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname:
                self.current.bind(alias.asname, "import", node)
            else:
                top = alias.name.split(".")[0]
                kind = "dotted_import" if "." in alias.name else "import"
                self.current.bind(top, kind, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            self.current.bind(alias.asname or alias.name, "import", node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.pattern is not None:
            self.visit(node.pattern)
        if node.name:
            self.current.bind(node.name, "local", node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self.current.bind(node.name, "local", node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        for key in node.keys:
            self.visit(key)
        for pattern in node.patterns:
            self.visit(pattern)
        if node.rest:
            self.current.bind(node.rest, "local", node)

    def visit_MatchClass(self, node: ast.MatchClass) -> None:
        self.visit(node.cls)
        for pattern in node.patterns:
            self.visit(pattern)
        for pattern in node.kwd_patterns:
            self.visit(pattern)

    def _visit_comprehension(self, node: ast.AST, elt_nodes: list[ast.AST]) -> None:
        generators = node.generators
        if not generators:
            for elt in elt_nodes:
                self.visit(elt)
            return
        self.visit(generators[0].iter)
        scope = self._push(ScopeKind.COMPREHENSION, node)
        node._scope = scope
        self._bind_target(generators[0].target)
        for cond in generators[0].ifs:
            self.visit(cond)
        for gen in generators[1:]:
            self.visit(gen.iter)
            self._bind_target(gen.target)
            for cond in gen.ifs:
                self.visit(cond)
        for elt in elt_nodes:
            self.visit(elt)
        self._pop()

    def _bind_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self.current.bind(target.id, "local", target)
            self._record(target, self.current)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._bind_target(elt)
        elif isinstance(target, ast.Starred):
            self._bind_target(target.value)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node, [node.elt])

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node, [node.elt])

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node, [node.elt])

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node, [node.key, node.value])

    def visit_TypeAlias(self, node) -> None:
        for tp in getattr(node, "type_params", None) or ():
            name = getattr(tp, "name", None)
            if name:
                self.type_params.add(name)
                self.current.bind(name, "typeparam", tp)
            bound = getattr(tp, "bound", None)
            if bound is not None:
                self.visit(bound)
        if isinstance(node.name, ast.Name):
            self.current.bind(node.name.id, "local", node.name)
        self.visit(node.value)


def _param_order(args: ast.arguments) -> list[str]:
    order = [a.arg for a in args.posonlyargs]
    order += [a.arg for a in args.args]
    if args.vararg is not None:
        order.append(args.vararg.arg)
    order += [a.arg for a in args.kwonlyargs]
    if args.kwarg is not None:
        order.append(args.kwarg.arg)
    return order


class SymbolTable:

    def __init__(self, tree: ast.Module) -> None:
        builder = ScopeBuilder()
        builder.visit(tree)
        self.tree = tree
        self.module = builder.module
        self.node_scope = builder.node_scope
        self.classes = builder.classes
        self.functions = builder.functions
        self.type_params = builder.type_params
        self._resolve_bases()

    def scope_of(self, node: ast.AST) -> Optional[Scope]:
        return self.node_scope.get(id(node))

    def scopes(self) -> Iterator[Scope]:
        return self.module.walk()

    def resolve_load(self, scope: Optional[Scope], name: str) -> Optional[Binding]:
        if scope is None:
            return None
        if name in scope.globals:
            return self.module.names.get(name)
        if name in scope.nonlocals:
            return self._find_enclosing_function(scope.parent, name)
        current: Optional[Scope] = scope
        while current is not None:
            if current.kind is ScopeKind.CLASS:
                if current is scope and name in current.names:
                    return current.names[name]
            else:
                if name in current.names:
                    return current.names[name]
                if name in current.globals:
                    return self.module.names.get(name)
            current = current.parent
        return None

    def resolve_store(self, scope: Optional[Scope], name: str) -> Optional[Binding]:
        if scope is None:
            return None
        if name in scope.globals:
            return self.module.names.get(name)
        if name in scope.nonlocals:
            return self._find_enclosing_function(scope.parent, name)
        return scope.names.get(name)

    def _find_enclosing_function(
        self, scope: Optional[Scope], name: str
    ) -> Optional[Binding]:
        while scope is not None:
            if scope.kind in _FUNCTION_SCOPES and name in scope.names:
                return scope.names[name]
            scope = scope.parent
        return None

    def enclosing_class(self, scope: Optional[Scope]) -> Optional[ClassInfo]:
        while scope is not None:
            info = scope.func_info
            if (
                scope.kind in _FUNCTION_SCOPES
                and info is not None
                and info.owner is not None
            ):
                return info.owner
            scope = scope.parent
        return None

    def _resolve_bases(self) -> None:
        module = self.module
        for info in self.classes.values():
            resolved: list[ClassInfo] = []
            for base in info.bases:
                target = self.class_of_expr(base, module)
                if target is not None and target is not info:
                    resolved.append(target)
            info.resolved_bases = resolved

    def class_of_expr(
        self, expr: ast.AST, scope: Optional[Scope]
    ) -> Optional[ClassInfo]:
        if isinstance(expr, ast.Name):
            binding = self.resolve_load(scope, expr.id)
            if binding is not None and isinstance(binding.node, ast.ClassDef):
                return self.classes.get(id(binding.node))
        return None
