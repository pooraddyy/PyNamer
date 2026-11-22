from __future__ import annotations

import contextlib
import io

import pytest

from pynamer import rename


def _execute(source: str) -> str:
    buffer = io.StringIO()
    code = compile(source, "<pynamer-test>", "exec")
    with contextlib.redirect_stdout(buffer):
        exec(code, {})
    return buffer.getvalue()


@pytest.fixture
def run_stdout():
    return _execute


@pytest.fixture
def check():

    def _check(source: str, *, expect_change: bool = True, **config) -> str:
        expected = _execute(source)
        obfuscated = rename(source, **config)
        if expect_change:
            assert obfuscated != source
        actual = _execute(obfuscated)
        assert actual == expected, (
            "behaviour changed after obfuscation\n"
            f"--- original ---\n{source}\n"
            f"--- obfuscated ---\n{obfuscated}"
        )
        return obfuscated

    return _check
