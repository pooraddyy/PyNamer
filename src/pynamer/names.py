from __future__ import annotations

import hashlib
import random
import string
from .config import NameStrategy

_ALPHA = string.ascii_letters + "_"
_ALPHANUM = string.ascii_letters + string.digits + "_"
_B62 = string.ascii_letters + string.digits


def _base62(value: int) -> str:
    if value == 0:
        return "0"
    out = []
    while value:
        value, rem = divmod(value, 62)
        out.append(_B62[rem])
    return "".join(reversed(out))


class NameFactory:

    def __init__(
        self,
        *,
        strategy: NameStrategy = NameStrategy.SEQUENTIAL,
        seed: int = 0,
        prefix: str = "_0x",
        reserved: object = (),
    ) -> None:
        self._strategy = NameStrategy(strategy)
        self._seed = int(seed)
        self._prefix = prefix or ""
        self._used: set[str] = set(reserved)
        self._counter = 0
        self._rng = random.Random(self._seed)

    def reserve(self, name: str) -> None:
        self._used.add(name)

    def reserve_many(self, names) -> None:
        self._used.update(names)

    def fresh(self, source: str = "") -> str:
        while True:
            self._counter += 1
            candidate = self._render(source, self._counter)
            if candidate and candidate.isidentifier() and candidate not in self._used:
                self._used.add(candidate)
                return candidate

    @property
    def generated(self) -> frozenset[str]:
        return frozenset(self._used)

    def _render(self, source: str, n: int) -> str:
        strat = self._strategy
        if strat is NameStrategy.SEQUENTIAL:
            return f"{self._prefix}{n:x}"
        if strat is NameStrategy.BASE62:
            return f"{self._prefix}{_base62(n)}"
        if strat is NameStrategy.HASH:
            digest = hashlib.blake2b(
                f"{self._seed}:{source}:{n}".encode("utf-8"), digest_size=6
            ).hexdigest()
            return f"{self._prefix}{digest}"
        if strat is NameStrategy.RANDOM:
            body = "".join(self._rng.choice(_ALPHANUM) for _ in range(8))
            return f"{self._prefix}{body}"
        if strat is NameStrategy.WORDS:
            body = "".join(
                self._rng.choice(_ALPHA)
                + "".join(self._rng.choice(_ALPHANUM) for _ in range(3))
                for _ in range(2)
            )
            return body
        raise AssertionError(f"unhandled strategy {strat!r}")
