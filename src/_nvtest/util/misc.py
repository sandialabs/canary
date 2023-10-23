from argparse import Namespace
from types import SimpleNamespace
from typing import Any
from typing import Sequence
from typing import Union


def boolean(arg):
    if arg is None:
        return False
    elif isinstance(arg, bool):
        return arg
    elif isinstance(arg, str):
        return arg.lower() in ("1", "on", "true", "yes")
    return bool(arg)


def ns2dict(arg: Union[Namespace, SimpleNamespace]) -> dict:
    value: dict[str, Any] = dict(vars(arg))
    for name, item in value.items():
        if isinstance(item, SimpleNamespace):
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
