# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Named reduction policies for aggregating lists of values.

``Reducer`` wraps a callable with a name for introspection.  A set of
common reducer functions (``last_or_none``, ``first_or_none``, ``any_true``,
``all_true``, ``identity``, ``concat``, ``unique``, ``merge_dicts``) and
pre-built ``Reducer`` constants (``LAST``, ``FIRST``, ``ANY``, ``ALL``, etc.)
are provided for use with ``Field``.
"""

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
    """A named reduction policy over a list of values.

    Attributes:
        name: Human-readable name used for repr and debugging.
        fn: Callable that reduces a ``list[T]`` to a value of type ``R``.
    """

    name: str
    fn: Callable[[list[T]], R]

    def __call__(self, values: list[T]) -> R:
        return self.fn(values)


# --- common reducer functions ---


def last_or_none(values: list[T]) -> T | None:
    """Return the last element of ``values``, or ``None`` if empty."""
    return values[-1] if values else None


def first_or_none(values: list[T]) -> T | None:
    """Return the first element of ``values``, or ``None`` if empty."""
    return values[0] if values else None


def any_true(values: list[bool]) -> bool:
    """Return ``True`` if any element of ``values`` is truthy."""
    return any(values)


def all_true(values: list[bool]) -> bool:
    """Return ``True`` if all elements of ``values`` are truthy; ``False`` for empty lists."""
    return all(values) if values else False


def identity(values: list[T]) -> list[T]:
    """Return ``values`` unchanged."""
    return values


def concat(values: Sequence[Iterable[T]]) -> list[T]:
    """Flatten an iterable of iterables into a single list.

    Args:
        values: Sequence of iterables to concatenate.

    Returns:
        Flattened list of all elements.
    """
    out: list[T] = []
    for it in values:
        out.extend(list(it))
    return out


def unique(values: list[T]) -> list[T]:
    """Return ``values`` with duplicates removed, preserving insertion order.

    Args:
        values: Input list potentially containing duplicates.

    Returns:
        De-duplicated list in original order.
    """
    out: list[T] = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def merge_dicts(values: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge a list of dicts into one, with later entries taking precedence.

    Args:
        values: List of dictionaries to merge.

    Returns:
        Single merged dictionary.
    """
    merged: dict[str, Any] = {}
    for d in values:
        merged.update(d)
    return merged


# --- convenient prebuilt reducers (optional) ---

LAST: Reducer[Any, Any] = Reducer("last", last_or_none)
FIRST: Reducer[Any, Any] = Reducer("first", first_or_none)
IDENTITY: Reducer[Any, Any] = Reducer("identity", identity)

ANY: Reducer[bool, bool] = Reducer("any", any_true)
ALL: Reducer[bool, bool] = Reducer("all", all_true)
MERGE_DICTS: Reducer[dict[str, Any], dict[str, Any]] = Reducer("merge_dicts", merge_dicts)
