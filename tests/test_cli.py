from __future__ import annotations

import io
import sys

import pytest

from pynamer.__main__ import main


def test_cli_reads_stdin_writes_stdout(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("def f():\n    return 1\n"))
    code = main([])
    assert code == 0
    out = capsys.readouterr().out
    assert out.strip().startswith("def ")


def test_cli_writes_file_and_stats(tmp_path, capsys):
    src = tmp_path / "m.py"
    src.write_text("def f():\n    return len([1, 2])\n")
    dst = tmp_path / "out.py"
    code = main([str(src), "-o", str(dst), "--builtins", "--stats"])
    assert code == 0
    assert dst.read_text()
    assert "pynamer:" in capsys.readouterr().err


def test_cli_map_out_and_in(tmp_path, capsys):
    src = tmp_path / "m.py"
    src.write_text("def api():\n    return 1\n")
    map_path = tmp_path / "map.json"
    code = main([str(src), "--map-out", str(map_path)])
    assert code == 0
    assert map_path.exists()

    code = main([str(src), "--map-in", str(map_path)])
    assert code == 0


def test_cli_missing_file_errors():
    with pytest.raises(SystemExit) as exc:
        main(["does-not-exist-1234.py"])
    assert exc.value.code == 2
