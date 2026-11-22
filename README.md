<h1 align="center">PyNamer</h1>

<p align="center">
  <b>A scope-aware Python source renamer / obfuscator that survives the hard cases.</b><br>
  Closures, <code>global</code> / <code>nonlocal</code>, keyword arguments, inheritance,
  comprehensions, walrus, <code>match</code>, <code>__slots__</code> and attributes - plus
  keyed hiding of string literals (URLs, tokens, messages) and import names.
</p>

<p align="center">
  <a href="https://pypi.org/project/pynamerx/"><img alt="PyPI" src="https://img.shields.io/pypi/v/pynamerx.svg"></a>
  <a href="https://pypi.org/project/pynamerx/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/pynamerx.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
</p>

<p align="center">
  <a href="#install">Install</a> &nbsp;|&nbsp;
  <a href="#quick-start">Quick start</a> &nbsp;|&nbsp;
  <a href="#command-line">CLI</a> &nbsp;|&nbsp;
  <a href="#library-api">API</a> &nbsp;|&nbsp;
  <a href="#configuration">Configuration</a> &nbsp;|&nbsp;
  <a href="#examples">Examples</a>
</p>

---

PyNamer builds an **explicit scope tree** (much like CPython's own `symtable`),
performs a dedicated **attribute data-flow analysis**, and rewrites the AST in a
single, re-entrant pass. The result is a source-to-source transformation that
keeps behaviour intact while changing every name it can safely change.

```python
from pynamer import rename

obfuscated = rename(open("secret.py").read())
```

## How values are hidden

Renaming changes *names*; it leaves literal values readable. PyNamer closes that
gap:

- **String literals** (`"https://..."`, API tokens, log messages, dict keys,
  f-string text, docstrings and string annotations) are replaced with a keyed,
  hex-encoded token and a single module-level decoder is injected at the top of
  the file. The key is derived from the `seed`, so the same input always produces
  the same output. Behaviour is untouched - every token decodes back to the exact
  original string at runtime.
- **Import statements** are rewritten to `__import__` indirection, so the module
  names themselves disappear from the source:
  `import requests as r` becomes `r = __import__(<decoded "requests">)`.

Both passes are on by default and can be switched off with
`hide_strings=False` / `hide_imports=False`, or from the CLI with
`--no-hide-strings` / `--no-hide-imports`.

```python
source = 'API = "https://api.example.com/v1"\nprint(API)'
print(rename(source))
```

```python
_0x2 = b'H\xd0d\xd7\xf6\x9e\xb0q\xd0\xcb\xca\xe8\xaar\x1c\xb0'
def _0x0(t):
 return bytes((a ^ _0x2[i % len(_0x2)] for i, a in enumerate(bytes.fromhex(t)))).decode()
_0x1 = _0x0('20a410a785a49f5eb1bba3c6cf0a7ddd38bc01f995f1dd5ea6fa')
print(_0x1)
```

## Install

```bash
pip install pynamerx
```

Requires Python 3.10 or newer.

## Quick start

The simplest entry point takes source in and returns source out:

```python
from pynamer import rename

source = '''
def greet(name):
    message = "hello, " + name
    return message

print(greet("world"))
'''

print(rename(source))
```

Need more than a string? Use `process` to get the mapping, stats and the
resulting tree as well:

```python
from pynamer import process

result = process(source, strategy="hash", seed=1, builtins=True)

print(result.stats.as_dict())   # symbol / attribute / size statistics
print(result.mapping.symbols)   # {"greet": "_0x3", ...}
result.mapping.save("map.json")
```

## Command line

```bash
pynamer module.py -o module.obf.py --prefix _0x --strategy base62
pynamer module.py --builtins --hide-init --strip-docstrings --stats
pynamer module.py --no-hide-strings --no-hide-imports   # only rename names
cat module.py | pynamer - --strategy hash --seed 7
python -m pynamer module.py --map-out map.json   # reuse later with --map-in
```

## Library API

```python
from pynamer import process, rename, rename_ast, RenameConfig, NameStrategy, RenameMap

# 1. simplest form -> string in, string out
out = rename(source)

# 2. full result object
result = process(source, strategy="hash", seed=1, builtins=True)
print(result.stats.as_dict())      # {"symbols": ..., "attributes": ...}
print(result.mapping.symbols)      # {"my_func": "_0x3", ...}
result.mapping.save("map.json")

# 3. AST in, AST out
new_tree = rename_ast(result.tree)

# 4. explicit config object
cfg = RenameConfig(strategy=NameStrategy.BASE62, prefix="_", minify=True)
out = rename(source, config=cfg)

# 5. package-wide stable renaming
shared = RenameMap.load("map.json")
for path in ("a.py", "b.py"):
    process(open(path).read(), map=shared)
shared.save("map.json")
```

## Configuration

Every option is a field on
[`RenameConfig`](src/pynamer/config.py) and can be passed as a keyword argument
to `process` / `rename`.

| Option | Default | Meaning |
| --- | --- | --- |
| `strategy` | `"sequential"` | `sequential` / `hash` / `random` / `base62` / `words` |
| `seed` | `0` | seed for deterministic strategies |
| `prefix` | `"_0x"` | prefix for generated identifiers |
| `minify` | `True` | single-space indentation, no blank lines |
| `strip_docstrings` | `False` | drop module / class / function docstrings |
| `builtins` | `False` | alias builtins (`print`, `len`, ...) at the top of the module |
| `hide_init` | `False` | obscure explicit constructors behind a forwarding method |
| `track_instances` | `False` | also rename local `Foo()`-instance variables |
| `hide_strings` | `True` | encode string literals behind an injected runtime decoder |
| `hide_imports` | `True` | rewrite `import` statements to `__import__` indirection |
| `rename_attributes` | `True` | rename locally defined attributes |
| `rename_kwargs` | `True` | remap keyword arguments of resolvable calls |
| `preserve` | `()` | names to never rename |
| `preserve_attributes` | `()` | attributes to never rename |
| `preserve_public` | `False` | keep public (non-underscore) module names |
| `validate` | `True` | re-`compile()` the result, raising on breakage |
| `map` | `None` | a `RenameMap` for cross-module stability |

## Why it is more powerful

| Concern | Typical renamers | PyNamer |
| --- | --- | --- |
| Re-entrancy | module-level globals | full scope tree, no shared state |
| Attributes | rename everything / nothing | data-flow: only *locally defined* attributes, never externally observed ones |
| Keyword arguments | untouched / naive | remapped against the **resolved callee**, MRO-aware, incl. inherited `__init__` |
| Inheritance | blind | MRO walking for constructors & method kwargs |
| Comprehensions | leaky | correct Python 3 scoping (first iterable in the enclosing scope) |
| `getattr(obj, "x")` | broken | constant attribute strings remapped too |
| String literals | left readable | keyed encode + injected runtime decoder (URLs / tokens / messages, docstrings and annotations hidden) |
| Imports | module names visible in source | rewritten to `__import__` indirection |
| Names | readable `_0x1` | deterministic or hashed / compacted, collision-free |
| Minifier | monkey-patches the unparser | auditable token-aware whitespace pass |
| Cross-module | none | `RenameMap` gives package-wide, stable names |
| Safety | none | optional `compile()` validation, preservation lists |

## What is deliberately not renamed

<details>
<summary>Expand the list of protected names</summary>

- `__dunder__` names and the `super` builtin (zero-arg `super()` relies on the
  literal name for the `__class__` cell).
- `visit_*` methods by default (they form the `ast.NodeVisitor` protocol).
- `from __future__ import ...` feature names (they are compiler flags).
- Attributes that also appear on objects PyNamer cannot reason about, and any
  attribute reached through `super()` unless it is defined on a *local* base.
- Names listed in `preserve` / `preserve_attributes`.
- String literals that must stay literal for the program to compile: `match`
  patterns (`case "x":`, mapping keys) and PEP 695 `type` alias values. Everything
  else - docstrings, annotations / forward references, and f-string text while
  leaving format specs intact - is encoded.
- Parameter names that are passed as a keyword at a call site whose callee
  cannot be resolved statically (for example `receiver.method(x=1)` on an
  unknown object, or any `**mapping` call) - renaming them would silently break
  the call, so they keep their spelling.

</details>

## Known limitations

<details>
<summary>Expand the list of caveats</summary>

Renaming is a semantics-preserving source transformation *up to* reflection:

- A renamed class / function reports its new `__name__` / `__qualname__`, and an
  `Enum` member's `.name` reflects the new spelling. Because docstrings are
  encoded by default, `__doc__` becomes `None` (and is dropped entirely with
  `strip_docstrings=True`); annotations are stored as decoder calls, so the raw
  `__annotations__` text differs, though `typing.get_type_hints` still resolves
  the same values. Avoid depending on those strings, or list the symbol in
  `preserve` / `preserve_attributes`.
- Dynamic name lookups via `globals()`, `eval`, `locals()` or non-constant
  `getattr(obj, some_variable)` cannot be tracked. Constant
  `getattr` / `setattr` / `hasattr` / `delattr` **are** handled.
- Attributes of classes whose bases live outside the processed source are left
  untouched (safe by default).
- `hide_imports` leaves relative imports (`from . import x`) and
  `from ... import *` untouched, since their module name is resolved by the
  package at runtime.
- `hide_strings` trades size for secrecy: encoded literals are larger than the
  originals they replace.

</details>

## Examples

Runnable examples live in [`examples/`](examples):

```bash
python examples/demo.py                                   # end-to-end demonstration
python examples/obfuscate.py examples/demo.py             # obfuscate & verify a real file
python examples/obfuscate.py examples/demo.py -o out.py --builtins
```

- `examples/demo.py` - a self-contained demonstration that renames an embedded
  module with several configurations and asserts the behaviour never changes.
- `examples/obfuscate.py` - obfuscates a given file through the library API and
  verifies the obfuscated module still produces identical output.
