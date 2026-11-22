from __future__ import annotations

import ast

import pytest

from pynamer import (
    ConfigurationError,
    RenameConfig,
    NameStrategy,
    process,
    rename,
    rename_ast,
)


def test_default_config_roundtrip():
    cfg = RenameConfig()
    assert cfg.minify is True
    assert cfg.strategy is NameStrategy.SEQUENTIAL
    assert cfg.hide_strings is True
    assert cfg.hide_imports is True


def test_config_merge_ignores_none():
    cfg = RenameConfig().merged(minify=None, seed=5)
    assert cfg.minify is True
    assert cfg.seed == 5


def test_config_unknown_option_raises():
    with pytest.raises(ConfigurationError):
        RenameConfig().merged(nope=True)


def test_invalid_prefix_raises():
    with pytest.raises(ConfigurationError):
        RenameConfig(prefix="9bad")


def test_preserve_names():
    out = rename("def helper():\n    return 1\n", preserve=["helper"])
    assert "helper" in out


def test_preserve_public():
    out = rename(
        "def public_api():\n    return 1\n\ndef _private():\n    return 2\n",
        preserve_public=True,
    )
    assert "public_api" in out
    assert "_private" not in out


def test_rename_attributes_disabled():
    source = "class C:\n    def __init__(self):\n        self.value = 1\n"
    out = rename(source, rename_attributes=False)
    assert ".value" in out
    assert ".value" not in rename(source, rename_attributes=True)


def test_preserve_attributes():
    source = (
        "class C:\n"
        "    def __init__(self):\n"
        "        self.keep = 1\n"
        "        self.drop = 2\n"
    )
    out = rename(source, preserve_attributes=["keep"])
    assert ".keep" in out
    assert ".drop" not in out


def test_strategy_determinism():
    source = "def compute(a, b):\n    return a + b\n"
    first = rename(source, strategy="hash", seed=42)
    second = rename(source, strategy="hash", seed=42)
    assert first == second


def test_builtin_names_never_remapped_by_default():
    out = rename("def f():\n    return len([1])\n")
    assert "len(" in out


def test_future_import_name_preserved():
    out = rename("from __future__ import annotations\n\ndef f() -> int:\n    return 1\n")
    assert "from __future__ import annotations" in out


def test_validate_produces_compilable_output():
    result = process("def f(x):\n    return x\n")
    compile(result.source, "<check>", "exec")


def test_missing_validation_can_be_disabled():
    result = process("def f():\n    return 1\n", validate=False)
    assert result.source


def test_rename_ast_returns_module():
    tree = rename_ast("def f():\n    return 1\n")
    assert isinstance(tree, ast.Module)
    compile(tree, "<check>", "exec")
