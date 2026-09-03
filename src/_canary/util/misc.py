# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Miscellaneous small utility functions used throughout canary.

Includes type coercion (``boolean``), namespace conversion (``ns2dict``),
sequence helpers (``dedup``, ``partition``, ``argsort``), and integer
digit-counting (``digits``).
"""

from argparse import Namespace
from types import SimpleNamespace
from typing import Any
from typing import Callable
from typing import Sequence


def boolean(arg: Any) -> bool:
    """Coerce ``arg`` to a Python bool using canary's truth conventions.

    ``None``, ``"0"``, ``"off"``, ``"false"``, and ``"no"`` are falsy; all
    other non-empty strings and truthy objects are truthy.

    Args:
        arg: Value to coerce.

    Returns:
        Boolean interpretation of ``arg``.
    """
    if arg is None:
        return False
    elif isinstance(arg, bool):
        return arg
    elif isinstance(arg, str):
        return arg.lower() not in ("0", "off", "false", "no")
    return bool(arg)


def ns2dict(arg: Namespace | SimpleNamespace) -> dict:
    """Recursively convert a ``Namespace`` or ``SimpleNamespace`` to a plain dict.

    Args:
        arg: The namespace to convert.

    Returns:
        Dictionary representation with nested namespaces also converted.
    """
    value: dict[str, Any] = dict(vars(arg))
    for name, item in value.items():
        if isinstance(item, (SimpleNamespace, Namespace)):
            value[name] = ns2dict(item)
    return value


def dedup(arg: Sequence[Any]) -> list[Any]:
    """Remove duplicates from ``arg`` while preserving insertion order.

    Args:
        arg: Input sequence, possibly containing duplicate values.

    Returns:
        List with first occurrences only, in original order.
    """
    result: list[Any] = []
    for item in arg:
        if item not in result:
            result.append(item)
    return result


def digits(x: int) -> int:
    """Return the number of decimal digits required to represent ``x``.

    Args:
        x: Non-negative integer.

    Returns:
        Number of decimal digits (minimum 1).
    """
    i, n = 1, 10
    while True:
        if x < n:
            return i
        i += 1
        n *= 10


def partition(sequence: list, predicate: Callable) -> tuple[list, list]:
    """Split ``sequence`` into two lists based on ``predicate``.

    Args:
        sequence: Input list to partition.
        predicate: Callable that returns ``True`` for items to put in the first list.

    Returns:
        A tuple ``(matching, non_matching)`` where ``matching`` contains items
        for which ``predicate`` returned ``True``.
    """
    first, second = [], []
    for item in sequence:
        if predicate(item):
            first.append(item)
        else:
            second.append(item)
    return first, second


def argsort(sequence: Sequence) -> list[int]:
    """Return the indices that would sort ``sequence``.

    Args:
        sequence: Sequence of comparable elements.

    Returns:
        List of indices such that ``[sequence[i] for i in argsort(sequence)]``
        is sorted in ascending order.
    """
    # http://stackoverflow.com/questions/3071415/efficient-method-to-calculate-the-rank-vector-of-a-list-in-python
    return sorted(range(len(sequence)), key=sequence.__getitem__)
