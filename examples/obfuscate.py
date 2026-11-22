from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pynamer import process


def run_source(source: str, filename: str) -> str:
    namespace: dict = {"__name__": "__main__", "__file__": os.path.abspath(filename)}
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exec(compile(source, filename, "exec"), namespace)
    return buffer.getvalue()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Obfuscate a Python file with PyNamer and verify it still runs."
    )
    parser.add_argument("source", help="path to the Python file to obfuscate")
    parser.add_argument("-o", "--output", help="write the result here instead of stdout")
    parser.add_argument("--strategy", default="sequential")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--prefix", default="_0x")
    parser.add_argument("--no-minify", action="store_true")
    parser.add_argument("--builtins", action="store_true")
    parser.add_argument("--hide-init", action="store_true")
    parser.add_argument("--strip-docstrings", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    original = open(args.source).read()

    result = process(
        original,
        filename=args.source,
        config=None,
        strategy=args.strategy,
        seed=args.seed,
        prefix=args.prefix,
        minify=not args.no_minify,
        builtins=args.builtins,
        hide_init=args.hide_init,
        strip_docstrings=args.strip_docstrings,
    )

    before = run_source(original, args.source)
    after = run_source(result.source, args.source)
    status = "identical" if before == after else "DIFFERENT"

    print(
        f"symbols={result.stats.symbols} attributes={result.stats.attributes} "
        f"builtins={result.stats.builtins} "
        f"size {result.stats.input_size} -> {result.stats.output_size} "
        f"behaviour={status}",
        file=sys.stderr,
    )

    if args.output:
        with open(args.output, "w") as fh:
            fh.write(result.source)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(result.source)

    return 0 if before == after else 1


if __name__ == "__main__":
    raise SystemExit(main())
