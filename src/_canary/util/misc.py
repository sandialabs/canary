# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from argparse import Namespace
from types import SimpleNamespace
from typing import Any
from typing import Callable
from typing import Sequence


def boolean(arg: Any) -> bool:
    if arg is None:
        return False
    elif isinstance(arg, bool):
        return arg
    elif isinstance(arg, str):
        return arg.lower() not in ("0", "off", "false", "no")
    return bool(arg)


def ns2dict(arg: Namespace | SimpleNamespace) -> dict:
    value: dict[str, Any] = dict(vars(arg))
    for name, item in value.items():
        if isinstance(item, (SimpleNamespace, Namespace)):
            value[name] = ns2dict(item)
    return value


def dedup(arg: Sequence[Any]) -> list[Any]:
    result: list[Any] = []
    for item in arg:
        if item not in result:
            result.append(item)
    return result


def digits(x: int) -> int:
    i, n = 1, 10
    while True:
        if x < n:
            return i
        i += 1
        n *= 10


def partition(sequence: list, predicate: Callable) -> tuple[list, list]:
    first, second = [], []
    for item in sequence:
        if predicate(item):
            first.append(item)
        else:
            second.append(item)
    return first, second


def argsort(sequence: Sequence) -> list[int]:
    # http://stackoverflow.com/questions/3071415/efficient-method-to-calculate-the-rank-vector-of-a-list-in-python
    return sorted(range(len(sequence)), key=sequence.__getitem__)
