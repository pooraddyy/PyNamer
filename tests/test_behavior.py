from __future__ import annotations

import pytest

SNIPPETS = {
    "simple_functions": """
def greet(name, *, loud=False):
    message = "hi " + name
    if loud:
        message = message.upper()
    return message

def main():
    print(greet("bob"))
    print(greet("eve", loud=True))

main()
""",
    "closures_global_nonlocal": """
counter = 0
def make_adder(base):
    total = base
    def add(n):
        nonlocal total
        global counter
        counter += 1
        total += n
        return total
    return add

def main():
    a = make_adder(10)
    print(a(1), a(2), a(3))
    print(counter)

main()
""",
    "comprehensions_walrus": """
def main():
    squares = [n * n for n in range(5) if (m := n % 2) == 0]
    table = {k: v for k, v in zip("ab", [1, 2])}
    unique = {x % 3 for x in range(10)}
    gen = sum(y for y in range(4))
    print(squares, table, sorted(unique), gen)

main()
""",
    "match_statement": """
def classify(value):
    match value:
        case [x, y]:
            return ("pair", x + y)
        case {"k": k, **rest}:
            return ("map", k, sorted(rest))
        case str() as text:
            return ("text", text)
        case _:
            return ("other",)

def main():
    print(classify([1, 2]))
    print(classify({"k": 5, "z": 9}))
    print(classify("hello"))
    print(classify(3.14))

main()
""",
    "classes_inheritance": """
class Animal:
    sounds = "..."
    def __init__(self, name, *, age=0):
        self.name = name
        self.age = age
    def speak(self):
        return self.name + " says " + self.sounds

class Dog(Animal):
    def __init__(self, name, breed):
        super().__init__(name, age=3)
        self.breed = breed
    def speak(self):
        return super().speak() + " (" + self.breed + ")"

def main():
    d = Dog("Rex", "lab")
    print(d.speak(), d.age, Animal.sounds)

main()
""",
    "slots_getattr": """
class Point:
    __slots__ = ("x", "y")
    def __init__(self, x, y=0):
        self.x = x
        self.y = y
    def norm(self):
        return self.x * self.x + self.y * self.y

def main():
    p = Point(3, y=4)
    print(getattr(p, "x"), hasattr(p, "y"), p.norm())
    setattr(p, "x", 6)
    print(hasattr(p, "z"), p.norm())

main()
""",
    "decorators": """
def trace(fn):
    def wrapper(*args, **kwargs):
        return ("traced", fn(*args, **kwargs))
    return wrapper

class Math:
    @staticmethod
    def double(x):
        return x * 2
    @classmethod
    def triple(cls, x):
        return cls.double(x) + x
    @property
    def value(self):
        return 42

@trace
def add(a, b):
    return a + b

def main():
    print(add(2, 3))
    print(Math.double(4), Math.triple(4))
    print(Math().value)

main()
""",
    "control_flow": """
def main():
    out = []
    for i in range(6):
        if i == 1:
            continue
        if i == 4:
            break
        try:
            if i == 3:
                raise ValueError("boom")
            out.append(i)
        except ValueError as exc:
            out.append(str(exc))
        else:
            out.append("ok")
        finally:
            out.append("f")
    print(out)

main()
""",
    "deletion_and_unpack": """
def main():
    a, *rest = [1, 2, 3, 4]
    (b, c) = (5, 6)
    d = {"k": 1}
    d["k2"] = 2
    del d["k"]
    x = 1
    del x
    print(a, rest, b, c, sorted(d))

main()
""",
    "lambdas_nested": """
def main():
    apply = lambda f, v: f(v)
    inc = lambda n: n + 1
    print(apply(inc, 10))
    def outer(a):
        def inner(b):
            return a + b
        return inner
    add5 = outer(5)
    print(add5(7))

main()
""",
    "star_args": """
def collect(*args, **kwargs):
    return sum(args), sorted(kwargs.items())

def main():
    print(collect(1, 2, 3, x=1, y=2))
    nums = [4, 5]
    print(collect(*nums))
    opts = {"a": 1}
    print(collect(**opts))

main()
""",
    "with_and_annotations": """
class Ctx:
    def __enter__(self):
        return 7
    def __exit__(self, *exc):
        return False

def main():
    total: int = 0
    with Ctx() as value:
        total += value
    print(total)

main()
""",
    "instance_tracking": """
class Counter:
    def __init__(self):
        self.n = 0

def main():
    c = Counter()
    c.n += 1
    d = Counter()
    d.n += 10
    print(c.n + d.n)

main()
""",
    "unknown_receiver_kwargs": """
class Base:
    def __init__(self, *, size=1):
        self.size = size
    def grow(self, *, step=2):
        return self.size + step

class Child(Base):
    def grow(self, *, step=2, bonus=0):
        return super().grow(step=step) + bonus

def main():
    items = [Child(size=3), Child(size=5)]
    print([item.grow(step=1, bonus=10) for item in items])

main()
""",
}


@pytest.mark.parametrize("name", sorted(SNIPPETS))
def test_behaviour_preserved(name, check):
    check(SNIPPETS[name])


@pytest.mark.parametrize("name", sorted(SNIPPETS))
def test_behaviour_preserved_minify_off(name, check):
    check(SNIPPETS[name], minify=False)


@pytest.mark.parametrize("strategy", ["sequential", "hash", "random", "base62", "words"])
def test_strategies_preserve_behaviour(strategy, check):
    check(SNIPPETS["classes_inheritance"], strategy=strategy)


def test_hide_init_preserves_behaviour(check):
    original = SNIPPETS["classes_inheritance"]
    obfuscated = check(original, hide_init=True)
    assert "_pynamer_init_" not in obfuscated


def test_builtins_preserves_behaviour(check):
    source = """
def main():
    data = [3, 1, 2]
    print(len(data), max(data), min(data), sorted(data))
    print(sum(range(5)), abs(-2), round(1.5))

main()
"""
    obfuscated = check(source, builtins=True)
    assert "(print, len," in obfuscated


def test_strip_docstrings(check):
    source = '''
"""module doc"""
def main():
    """function doc"""
    print("doc-hidden")

main()
'''
    obfuscated = check(source, strip_docstrings=True)
    assert "module doc" not in obfuscated
    assert "function doc" not in obfuscated


def test_subclass_of_external_type(check):
    source = '''
class MyDict(dict):
    def get(self, key):
        return super().get(key, "missing")

def main():
    d = MyDict(a=1)
    print(d.get("a"), d.get("b"))

main()
'''
    obfuscated = check(source)
    assert "super().get(" in obfuscated


def test_hide_strings_removes_literals(check):
    source = '''
API = "https://api.example.com/v1"
TOKEN = "sk_live_secret"

def main():
    print(API + "/users", TOKEN)

main()
'''
    obfuscated = check(source)
    assert "https://api.example.com/v1" not in obfuscated
    assert "sk_live_secret" not in obfuscated


def test_hide_strings_can_be_disabled(check):
    source = 'def main():\n    print("https://api.example.com/v1")\n\nmain()\n'
    obfuscated = check(source, hide_strings=False)
    assert "https://api.example.com/v1" in obfuscated


def test_hide_strings_keeps_match_and_fstrings_working(check):
    source = '''
def classify(value):
    match value:
        case "yes":
            return "matched"
        case _:
            return f"k={value}"

def main():
    print(classify("yes"))
    print(classify(3))

main()
'''
    obfuscated = check(source)
    assert "matched" not in obfuscated


def test_hide_strings_hides_docstrings_and_annotations(check):
    source = '''
"""docs https://doc.example.com"""
def main(x: "https://anno.example.com") -> "https://ret.example.com":
    """inner https://inner.example.com"""
    print(x, "https://body.example.com")

main("hi")
'''
    obfuscated = check(source)
    assert "https://doc.example.com" not in obfuscated
    assert "https://anno.example.com" not in obfuscated
    assert "https://ret.example.com" not in obfuscated
    assert "https://inner.example.com" not in obfuscated
    assert "https://body.example.com" not in obfuscated


def test_hide_strings_fstring_only_source_injects_decoder(check):
    source = '''
def main():
    value = 42
    print(f"value={value:>5}|")

main()
'''
    obfuscated = check(source)
    assert "value=" not in obfuscated
    assert ":>5}" in obfuscated


def test_hide_strings_keeps_future_annotations_working(check):
    source = '''from __future__ import annotations

def main(x: "https://anno.example.com") -> "https://ret.example.com":
    return x

print(main("ok"))
'''
    obfuscated = check(source)
    assert "https://anno.example.com" not in obfuscated
    assert "https://ret.example.com" not in obfuscated


def test_hide_strings_keeps_future_import_at_top(check):
    source = '''"""docs https://doc.example.com"""
from __future__ import annotations

import json

def main(x: "https://anno.example.com") -> "int":
    print(json.dumps({"x": x}), "https://body.example.com")
    return 1

main(2)
'''
    obfuscated = check(source)
    assert obfuscated.startswith("from __future__ import annotations")
    assert "https://doc.example.com" not in obfuscated
    assert "https://anno.example.com" not in obfuscated
    assert "https://body.example.com" not in obfuscated


def test_hide_imports_rewrites_statements(check):
    source = "import math\n\ndef main():\n    print(math.floor(2.9))\n\nmain()\n"
    obfuscated = check(source)
    assert "import math" not in obfuscated


def test_hide_imports_can_be_disabled(check):
    source = "import math\n\ndef main():\n    print(math.floor(2.9))\n\nmain()\n"
    obfuscated = check(source, hide_imports=False)
    assert "import math" in obfuscated

