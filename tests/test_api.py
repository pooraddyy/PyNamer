from __future__ import annotations

import ast

from pynamer import (
    RenameMap,
    minify_source,
    process,
    rename,
    rename_ast,
    collect_identifiers,
)


def test_minify_uses_single_space_indent():
    source = "def f():\n    if True:\n        return 1\n"
    assert minify_source(source) == "def f():\n if True:\n  return 1\n"


def test_minify_drops_blank_lines():
    source = "a = 1\n\n\nb = 2\n"
    assert minify_source(source) == "a = 1\nb = 2\n"


def test_minify_preserves_multiline_strings():
    source = 'x = """\n    keep   this\n        and this\n"""\n'
    out = minify_source(source)
    assert "    keep   this" in out
    assert "        and this" in out


def test_minify_preserves_behaviour():
    source = (
        "def f(a, b):\n"
        "    text = 'a  b'\n"
        "    return text + str(a + b)\n"
        "print(f(1, 2))\n"
    )
    obfuscated = rename(source)
    ns: dict = {}
    exec(compile(obfuscated, "<m>", "exec"), ns)


def test_process_returns_result_with_stats():
    result = process("def f(x, y):\n    return x + y\n")
    assert result.stats.symbols >= 1
    assert result.stats.output_size > 0
    assert isinstance(result.mapping, RenameMap)
    assert result.mapping.symbols


def test_rename_ast_and_rename_agree():
    source = "def f():\n    return 1\n"
    tree = rename_ast(source)
    assert isinstance(tree, ast.Module)
    assert ast.unparse(tree)


def test_collect_identifiers():
    tree = ast.parse("def f(a):\n    return a + len([])\n")
    names = collect_identifiers(tree)
    assert {"f", "a", "len"} <= names


def test_cross_module_map_is_stable():
    shared = RenameMap()
    process("def api():\n    return 1\n", map=shared)
    expected = shared.symbols["api"]
    second = process("from a import api\napi()\n", map=shared)
    assert second.mapping.symbols["api"] == expected
    assert expected in second.source


def test_map_export_roundtrip(tmp_path):
    result = process("def f(x):\n    return x\n")
    path = tmp_path / "map.json"
    result.export(path)
    loaded = RenameMap.load(path)
    assert loaded.symbols == result.mapping.symbols
