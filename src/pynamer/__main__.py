from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .api import process
from .config import NameStrategy, RenameConfig
from .errors import PynamerError
from .mapfile import RenameMap


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pynamer",
        description="Scope-aware Python source renamer / obfuscator.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="input .py file (reads stdin when omitted or '-')",
    )
    parser.add_argument("-o", "--output", help="write result here instead of stdout")
    parser.add_argument("--version", action="version", version=f"PyNamer {__version__}")

    naming = parser.add_argument_group("naming")
    naming.add_argument(
        "--strategy",
        choices=[s.value for s in NameStrategy],
        default=NameStrategy.SEQUENTIAL.value,
    )
    naming.add_argument("--seed", type=int, default=0)
    naming.add_argument("--prefix", default="_0x")

    passes = parser.add_argument_group("passes")
    passes.add_argument("--no-minify", action="store_true", help="keep readable spacing")
    passes.add_argument("--strip-docstrings", action="store_true")
    passes.add_argument("--builtins", action="store_true", help="alias builtin names")
    passes.add_argument("--hide-init", action="store_true")
    passes.add_argument("--track-instances", action="store_true")
    passes.add_argument("--no-attributes", action="store_true")
    passes.add_argument("--no-kwargs", action="store_true")
    passes.add_argument(
        "--no-hide-strings",
        action="store_true",
        help="keep string literals (URLs, tokens, messages) readable",
    )
    passes.add_argument(
        "--no-hide-imports",
        action="store_true",
        help="keep import statements instead of indirection",
    )

    safety = parser.add_argument_group("safety")
    safety.add_argument(
        "--preserve", nargs="*", default=None, help="names to never rename"
    )
    safety.add_argument(
        "--preserve-attributes", nargs="*", default=None, help="attributes to keep"
    )
    safety.add_argument("--preserve-public", action="store_true")
    safety.add_argument("--no-validate", action="store_true")

    maps = parser.add_argument_group("maps")
    maps.add_argument("--map-in", help="load a previous rename map (JSON)")
    maps.add_argument("--map-out", help="save the produced rename map (JSON)")

    parser.add_argument(
        "--stats", action="store_true", help="print a short report to stderr"
    )
    return parser


def _config_from_args(args: argparse.Namespace) -> RenameConfig:
    renaming_map = RenameMap.load(args.map_in) if args.map_in else None
    return RenameConfig(
        strategy=NameStrategy(args.strategy),
        seed=args.seed,
        prefix=args.prefix,
        minify=not args.no_minify,
        strip_docstrings=args.strip_docstrings,
        builtins=args.builtins,
        hide_init=args.hide_init,
        track_instances=args.track_instances,
        rename_attributes=not args.no_attributes,
        rename_kwargs=not args.no_kwargs,
        hide_strings=not args.no_hide_strings,
        hide_imports=not args.no_hide_imports,
        preserve=frozenset(args.preserve or ()),
        preserve_attributes=frozenset(args.preserve_attributes or ()),
        preserve_public=args.preserve_public,
        validate=not args.no_validate,
        map=renaming_map,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.source in (None, "-"):
        text = sys.stdin.read()
        filename = "<stdin>"
    else:
        path = Path(args.source)
        if not path.is_file():
            parser.error(f"no such file: {path}")
        text = path.read_text()
        filename = str(path)

    try:
        result = process(text, filename=filename, config=_config_from_args(args))
    except PynamerError as exc:
        print(f"pynamer: error: {exc}", file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(result.source)
    else:
        sys.stdout.write(result.source)

    if args.map_out:
        result.mapping.save(args.map_out)

    if args.stats:
        stats = result.stats
        print(
            "pynamer: "
            f"symbols={stats.symbols} attributes={stats.attributes} "
            f"builtins={stats.builtins} "
            f"size={stats.input_size}->{stats.output_size} (-{stats.saved})",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
