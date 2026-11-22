from __future__ import annotations

import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pynamer import process

SAMPLE = '''\
from __future__ import annotations

RATES = {"usd": 1.0, "eur": 0.92, "inr": 83.1}


class Money:

    def __init__(self, amount, currency="usd"):
        self.amount = amount
        self.currency = currency

    def convert(self, target):
        base = self.amount * RATES[self.currency]
        return Money(base / RATES[target], currency=target)

    def __repr__(self):
        return f"{self.amount:.2f} {self.currency.upper()}"


def total(prices, *, discount=0.0):
    running = 0.0
    for price in prices:
        running += price.amount
    return running * (1 - discount)


def describe(wallet):
    cheapest = min(wallet, key=lambda money: money.amount)
    return f"{len(wallet)} items, cheapest {cheapest!r}"


def main():
    wallet = [Money(10), Money(20).convert("eur"), Money(5, "inr")]
    print(describe(wallet))
    print(total(wallet, discount=0.1))


if __name__ == "__main__":
    main()
'''

CONFIGS = {
    "sequential + attributes + minify": {},
    "hashed names, no minify": {"strategy": "hash", "seed": 7, "minify": False},
    "builtins + hide_init + strip_docstrings": {
        "strategy": "base62",
        "prefix": "_",
        "builtins": True,
        "hide_init": True,
        "strip_docstrings": True,
    },
}


def behaviour(source: str, filename: str) -> str:
    namespace: dict = {"__name__": "__main__"}
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(compile(source, filename, "exec"), namespace)
    return buffer.getvalue()


def main() -> None:
    print("=" * 72)
    print("PyNamer demo")
    print("=" * 72)

    first = None
    for label, config in CONFIGS.items():
        result = process(SAMPLE, filename="sample.py", **config)
        if first is None:
            first = result
        print(f"\n### {label}")
        print(
            f"    symbols={result.stats.symbols} "
            f"attributes={result.stats.attributes} "
            f"builtins={result.stats.builtins} "
            f"size {result.stats.input_size} -> {result.stats.output_size}"
        )
        assert behaviour(SAMPLE, "<original>") == behaviour(
            result.source, "<obfuscated>"
        ), f"behaviour changed for {label!r}"

    print("\n" + "-" * 72)
    print("Obfuscated output (first configuration):")
    print("-" * 72)
    print(first.source)
    print("Behaviour is identical to the original for every configuration.")


if __name__ == "__main__":
    main()
