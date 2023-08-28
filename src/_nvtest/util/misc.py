from types import SimpleNamespace
from typing import Any


def boolean(arg):
    if arg is None:
        return False
    elif isinstance(arg, bool):
        return arg
    elif isinstance(arg, str):
        return arg.lower() in ("1", "on", "true", "yes")
    return bool(arg)


def ns2dict(arg: SimpleNamespace) -> dict:
    value: dict[str, Any] = dict(vars(arg))
    for (name, item) in value.items():
        if isinstance(item, SimpleNamespace):
            value[name] = ns2dict(item)
    return value
