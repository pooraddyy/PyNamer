from __future__ import annotations

import ast
import builtins
import keyword

BUILTIN_NAMES: frozenset[str] = frozenset(
    n for n in dir(builtins) if n != "super"
)

HARD_RESERVED: frozenset[str] = frozenset(keyword.kwlist) | frozenset(
    keyword.softkwlist
) | frozenset({"super", "__class__", "__dict__", "__slots__"})


def is_reserved_word(name: str) -> bool:
    return keyword.iskeyword(name) or keyword.issoftkeyword(name)


def is_renamable(name: str, *, keep_visit: bool = True) -> bool:
    if not name:
        return False
    if name.startswith("__"):
        return False
    if keep_visit and name.startswith("visit_"):
        return False
    if is_reserved_word(name):
        return False
    return True


def attr_is_renamable(name: str) -> bool:
    if not name:
        return False
    if name.startswith("__"):
        return False
    if name.startswith("visit_"):
        return False
    return True


def iter_child_nodes(node: ast.AST, *, include_attributes: bool = False):
    return ast.iter_child_nodes(node)


def target_names(target: ast.AST) -> set[str]:
    names: set[str] = set()
    stack = [target]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Starred):
            stack.append(node.value)
        elif isinstance(node, (ast.Tuple, ast.List)):
            stack.extend(node.elts)
    return names


def decorator_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return decorator_name(node.func)
    return None


def is_staticmethod(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(decorator_name(d) == "staticmethod" for d in fn.decorator_list)
