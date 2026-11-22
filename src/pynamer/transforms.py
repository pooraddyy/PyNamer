from __future__ import annotations

import ast
import random

__all__ = [
    "strip_docstrings",
    "apply_hide_init",
    "hide_imports",
    "hide_strings",
]


def strip_docstrings(tree: ast.Module) -> ast.Module:
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = node.body
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            del body[0]
            if not body and not isinstance(node, ast.Module):
                body.append(ast.Pass())
    return tree


def apply_hide_init(tree: ast.Module) -> ast.Module:
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    for index, cls in enumerate(classes):
        for pos, stmt in enumerate(cls.body):
            if isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__":
                hidden = f"_pynamer_init_{index}"
                stmt.name = hidden
                stmt._pynamer_freeze_params = True
                cls.body.insert(pos + 1, _forwarder(hidden))
                break
    return tree


def hide_imports(tree: ast.Module) -> ast.Module:
    return _ImportHider().visit(tree)


class _ImportHider(ast.NodeTransformer):
    def visit_Import(self, node: ast.Import) -> list[ast.stmt]:
        statements: list[ast.stmt] = []
        for alias in node.names:
            if alias.asname:
                target = alias.asname
                value = _call_import(alias.name, alias.name.rsplit(".", 1)[-1])
            elif "." in alias.name:
                target = alias.name.split(".", 1)[0]
                value = _call_import(alias.name, None)
            else:
                target = alias.name
                value = _call_import(alias.name, None)
            statements.append(_assignment(target, value, node))
        return statements

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.stmt | list[ast.stmt]:
        if node.level or node.module == "__future__":
            return node
        if node.module is None or any(alias.name == "*" for alias in node.names):
            return node
        statements: list[ast.stmt] = []
        for alias in node.names:
            target = alias.asname or alias.name
            base = _call_import(node.module, alias.name)
            value = ast.Call(
                func=ast.Name(id="getattr", ctx=ast.Load()),
                args=[base, ast.Constant(alias.name)],
                keywords=[],
            )
            statements.append(_assignment(target, value, node))
        return statements


def _call_import(module: str, leaf: str | None) -> ast.Call:
    call = ast.Call(
        func=ast.Name(id="__import__", ctx=ast.Load()),
        args=[ast.Constant(module)],
        keywords=[],
    )
    if leaf is not None:
        call.keywords.append(
            ast.keyword(
                arg="fromlist",
                value=ast.List(elts=[ast.Constant(leaf)], ctx=ast.Load()),
            )
        )
    return call


def _assignment(target: str, value: ast.AST, template: ast.stmt) -> ast.Assign:
    node = ast.Assign(
        targets=[ast.Name(id=target, ctx=ast.Store())],
        value=value,
    )
    return ast.copy_location(node, template)


def hide_strings(
    tree: ast.Module, *, seed: int = 0, prefix: str = "_0x"
) -> ast.Module:
    key = _keystream(seed)
    reserved = _identifiers(tree)
    decoder = _fresh(reserved, prefix)
    reserved.add(decoder)
    keyname = _fresh(reserved, prefix)

    hider = _StringHider(key, decoder)
    tree = hider.visit(tree)
    if not hider.used:
        return tree

    header = ast.parse(_decoder_source(decoder, keyname, key)).body
    index = _header_index(tree)
    tree.body[index:index] = header
    ast.fix_missing_locations(tree)
    return tree


class _StringHider(ast.NodeTransformer):
    def __init__(self, key: bytes, decoder: str) -> None:
        self.key = key
        self.decoder = decoder
        self.skip: set[int] = set()
        self.used = False

    def visit_Module(self, node: ast.Module) -> ast.Module:
        self._collect_skip(node)
        self.generic_visit(node)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, str) and id(node) not in self.skip:
            return self._call(node.value, node)
        return node

    def visit_JoinedStr(self, node: ast.JoinedStr) -> ast.AST:
        if id(node) in self.skip:
            return node
        values: list[ast.expr] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                call = self._call(value.value, value)
                wrapped = ast.FormattedValue(value=call, conversion=-1)
                values.append(ast.copy_location(wrapped, value))
            else:
                values.append(self.visit(value))
        node.values = values
        return node

    def visit_FormattedValue(self, node: ast.FormattedValue) -> ast.AST:
        node.value = self.visit(node.value)
        return node

    def _call(self, text: str, location: ast.AST) -> ast.Call:
        self.used = True
        token = _encode(text, self.key)
        call = ast.Call(
            func=ast.Name(id=self.decoder, ctx=ast.Load()),
            args=[ast.Constant(token)],
            keywords=[],
        )
        return ast.copy_location(call, location)

    def _collect_skip(self, tree: ast.Module) -> None:
        type_alias = getattr(ast, "TypeAlias", None)
        for node in ast.walk(tree):
            if isinstance(node, ast.match_case):
                self._skip_subtree(node.pattern)
            elif type_alias is not None and isinstance(node, type_alias):
                self._skip_subtree(node.value)

    def _skip_subtree(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            self.skip.add(id(child))


def _keystream(seed: int) -> bytes:
    rng = random.Random(seed if seed else 0x5EED)
    key = bytes(rng.randrange(256) for _ in range(16))
    return key if any(key) else b"\x51"


def _encode(text: str, key: bytes) -> str:
    span = len(key)
    data = text.encode("utf-8")
    return bytes(byte ^ key[i % span] for i, byte in enumerate(data)).hex()


def _decoder_source(decoder: str, keyname: str, key: bytes) -> str:
    literal = "".join(f"\\x{byte:02x}" for byte in key)
    return (
        f"{keyname} = b'{literal}'\n"
        f"def {decoder}(t):\n"
        f"    return bytes(a ^ {keyname}[i % len({keyname})]"
        f" for i, a in enumerate(bytes.fromhex(t))).decode()\n"
    )


def _identifiers(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split(".")[0])
    return names


def _fresh(reserved: set[str], prefix: str) -> str:
    index = 0
    while True:
        name = f"{prefix}{index}"
        if name not in reserved:
            return name
        index += 1


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


def _forwarder(hidden: str) -> ast.FunctionDef:
    return ast.FunctionDef(
        name="__init__",
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg="self")],
            vararg=ast.arg(arg="args"),
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=ast.arg(arg="kwargs"),
            defaults=[],
        ),
        body=[
            ast.Return(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="self", ctx=ast.Load()),
                        attr=hidden,
                        ctx=ast.Load(),
                    ),
                    args=[
                        ast.Starred(
                            value=ast.Name(id="args", ctx=ast.Load()),
                            ctx=ast.Load(),
                        )
                    ],
                    keywords=[
                        ast.keyword(
                            arg=None, value=ast.Name(id="kwargs", ctx=ast.Load())
                        )
                    ],
                )
            )
        ],
        decorator_list=[],
        returns=None,
    )
