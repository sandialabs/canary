from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Generic
from typing import Iterable
from typing import Sequence
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class Reducer(Generic[T, R]):
    """A named reduction policy over a list of values."""

    name: str
    fn: Callable[[list[T]], R]

    def __call__(self, values: list[T]) -> R:
        return self.fn(values)


# --- common reducer functions ---


def last_or_none(values: list[T]) -> T | None:
    return values[-1] if values else None


def first_or_none(values: list[T]) -> T | None:
    return values[0] if values else None


def any_true(values: list[bool]) -> bool:
    return any(values)


def all_true(values: list[bool]) -> bool:
    return all(values) if values else False


def identity(values: list[T]) -> list[T]:
    return values


def concat(values: Sequence[Iterable[T]]) -> list[T]:
    out: list[T] = []
    for it in values:
        out.extend(list(it))
    return out


def unique(values: list[T]) -> list[T]:
    out: list[T] = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def merge_dicts(values: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for d in values:
        merged.update(d)
    return merged


# --- convenient prebuilt reducers (optional) ---

LAST = Reducer("last", last_or_none)
FIRST = Reducer("first", first_or_none)
ANY = Reducer("any", any_true)
ALL = Reducer("all", all_true)
IDENTITY = Reducer("identity", identity)
MERGE_DICTS = Reducer("merge_dicts", merge_dicts)
