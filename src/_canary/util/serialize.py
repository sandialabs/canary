# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Any


def serialize(obj: Any) -> Any:
    """
    Recursively expand an object into JSON-serializable primitives, by applying
    __serialize__() to objects that define it.

    Similar in spirit to dataclasses.asdict(), but uses the library's serialization
    protocol and preserves the "__type__" tag so the result can be round-tripped with
    object_hook/__deserialize__.

    Returns
    -------
    Any
        A structure composed only of:
          - dict[str, Any]
          - list[Any]
          - str/int/float/bool/None
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Path):
        return obj.as_posix()
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): serialize(v) for k, v in obj.items()}
    if hasattr(obj, "__serialize__"):
        payload = dict(obj.__serialize__())
        return {k: serialize(v) for k, v in payload.items()}
    raise TypeError(f"Object of type {type(obj).__name__} is not serializable")
