from __future__ import annotations

from pynamer import RenameMap


def test_roundtrip_dict():
    rm = RenameMap(strategy="hash", seed=3, prefix="_", module="m.py")
    rm.symbols["foo"] = "_a"
    rm.attributes["bar"] = "_b"
    restored = RenameMap.from_dict(rm.to_dict())
    assert restored.strategy == "hash"
    assert restored.seed == 3
    assert restored.prefix == "_"
    assert restored.module == "m.py"
    assert restored.symbols == {"foo": "_a"}
    assert restored.attributes == {"bar": "_b"}


def test_save_load(tmp_path):
    rm = RenameMap()
    rm.symbols["x"] = "_0x1"
    path = tmp_path / "map.json"
    rm.save(path)
    assert RenameMap.load(path).symbols == {"x": "_0x1"}


def test_merge():
    a = RenameMap()
    a.symbols["x"] = "_0x1"
    b = RenameMap()
    b.symbols["y"] = "_0x2"
    b.attributes["a"] = "_0x3"
    merged = a.merge(b)
    assert merged.symbols == {"x": "_0x1", "y": "_0x2"}
    assert merged.attributes == {"a": "_0x3"}


def test_lookups_and_reverse():
    rm = RenameMap()
    rm.symbols["x"] = "_0x1"
    assert rm.lookup_symbol("x") == "_0x1"
    assert rm.lookup_symbol("missing") == "missing"
    assert rm.reverse_symbols() == {"_0x1": "x"}


def test_dunder_len_and_truthiness():
    rm = RenameMap()
    assert bool(rm) is True
    rm.symbols["a"] = "b"
    assert len(rm) == 1
