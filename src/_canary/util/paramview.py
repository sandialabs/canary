# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any
from typing import Generator

key_type = tuple[str, ...] | str
index_type = tuple[int, ...] | int


class Parameters:
    """Store parameters for a single test instance (case)

    Examples:

      >>> p = Parameters(a=1, b=2, c=3)
      >>> p['a']
      1
      >>> assert p.a == p['a']
      >>> p[('a', 'b')]
      (1, 2)
      >>> assert p['a,b'] == p[('a', 'b')]
      >>> p[('b', 'c', 'a')]
      (2, 3, 1)

    """

    def __init__(self, **kwargs: Any) -> None:
        self._keys: list[str] = list(kwargs.keys())
        self._values: list[Any] = list(kwargs.values())

    def __str__(self) -> str:
        name = self.__class__.__name__
        s = ", ".join(f"{k}={v}" for k, v in self.items())
        return f"{name}({s})"

    def __contains__(self, arg: key_type) -> bool:
        return self.multi_index(arg) is not None

    def __getitem__(self, arg: key_type) -> Any:
        ix = self.multi_index(arg)
        if ix is None:
            raise KeyError(arg)
        elif isinstance(ix, int):
            return self._values[ix]
        return tuple([self._values[i] for i in ix])

    def __getattr__(self, key: str) -> Any:
        if key not in self._keys:
            raise AttributeError(f"Parameters object has no attribute {key!r}")
        index = self._keys.index(key)
        return self._values[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Parameters):
            return self._keys == other._keys and self._values == other._values
        assert isinstance(other, dict)
        if len(self._keys) != len(other):
            return False
        for key, value in other.items():
            if key not in self._keys:
                return False
            if self._keys[key] != value:
                return False
        return True

    def __getstate__(self):
        return self.__dict__

    def __setstate__(self, state):
        self.__dict__ = state

    def multi_index(self, arg: key_type) -> index_type | None:
        keys: tuple[str, ...]
        if isinstance(arg, str):
            if arg in self._keys:
                value = self._keys.index(arg)
                if isinstance(value, list):
                    return tuple(value)
                return value
            elif "," in arg:
                keys = tuple(arg.split(","))
            else:
                return None
        else:
            keys = tuple(arg)
        return tuple([self._keys.index(key) for key in keys])

    def items(self) -> Generator[Any, None, None]:
        for i, key in enumerate(self._keys):
            yield key, self._values[i]

    def keys(self) -> list[str]:
        return list(self._keys)

    def values(self) -> list[Any]:
        return list(self._values)

    def get(self, key: str, default: Any | None = None) -> Any | None:
        try:
            return self[key]
        except KeyError:
            return default

    def asdict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for i, key in enumerate(self._keys):
            d[key] = self._values[i]
        return d


class MultiParameters(Parameters):
    """Store parameters for a single test instance (case)

    Examples:

      >>> p = Parameters(a=[1, 2, 3], b=[4, 5, 6], c=[7, 8, 9])
      >>> a = p['a']
      >>> a
      (1, 2, 3)
      >>> b = p['b']
      >>> b
      (4, 5, 6)
      >>> for i, values in enumerate(p[('a', 'b')]):
      ...     assert values == (a[i], b[i])
      ...     print(values)
      (1, 4)
      (2, 5)

      As a consequence of the above, note the following:

      >>> x = p[('a',)]
      >>> x
      ((1,), (2,), (3,))

      etc.

    """

    def __init__(self, **kwargs: Any) -> None:
        self._keys: list[str] = list(kwargs.keys())
        it = iter(kwargs.values())
        p_len = len(next(it))
        if not all(len(p) == p_len for p in it):
            raise ValueError(f"{self.__class__.__name__}: all arguments must be the same length")
        self._values: list[Any] = [tuple(_) for _ in kwargs.values()]

    def __getitem__(self, arg: key_type) -> Any:
        ix = self.multi_index(arg)
        if ix is None:
            raise KeyError(arg)
        elif isinstance(ix, int):
            return self._values[ix]
        rows = [self._values[i] for i in ix]
        # return colum data, now row data
        columns = tuple(zip(*rows))
        return columns
