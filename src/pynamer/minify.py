from __future__ import annotations

import io
import tokenize

__all__ = ["minify_source"]

_FSTRING_START = getattr(tokenize, "FSTRING_START", -1)
_FSTRING_END = getattr(tokenize, "FSTRING_END", -1)


def minify_source(source: str, *, indent: int = 1) -> str:
    protected = _protected_lines(source)
    out: list[str] = []
    for lineno, line in enumerate(source.split("\n"), start=1):
        if lineno in protected:
            out.append(line)
            continue
        stripped = line.rstrip()
        if not stripped.strip():
            continue
        lead = stripped[: len(stripped) - len(stripped.lstrip(" \t"))]
        level = len(lead.expandtabs(4)) // 4
        out.append(" " * (indent * level) + stripped.lstrip(" \t"))
    text = "\n".join(out)
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def _protected_lines(source: str) -> set[int]:
    protected: set[int] = set()
    fstring_start: int | None = None
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            kind = tok.type
            if kind == tokenize.STRING and tok.end[0] > tok.start[0]:
                protected.update(range(tok.start[0] + 1, tok.end[0] + 1))
            elif kind == _FSTRING_START:
                fstring_start = tok.start[0]
            elif kind == _FSTRING_END and fstring_start is not None:
                if tok.end[0] > fstring_start:
                    protected.update(range(fstring_start + 1, tok.end[0] + 1))
                fstring_start = None
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return set()
    return protected
