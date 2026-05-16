# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import importlib
import json
import json.decoder
import os
import time
from pathlib import Path
from typing import Any

from .filesystem import mkdirp
from .string import pluralize

JSONDecodeError = json.decoder.JSONDecodeError

__all__ = ["JSONDecodeError", "dump", "dumps", "dumps_min", "load", "loads", "try_loads"]


class Encoder(json.JSONEncoder):
    def default(self, o: Any):
        if isinstance(o, Path):
            return str(o.as_posix())
        elif isinstance(o, tuple):
            return list(o)
        elif hasattr(o, "__serialize__"):
            data = dict(o.__serialize__())
            data[".type"] = f"{o.__class__.__module__}::{o.__class__.__qualname__}"
            return data
        return json.JSONEncoder.default(self, o)


def _load_class(class_spec: str) -> Any:
    modulename, qualname = class_spec.split("::")
    module = importlib.import_module(modulename)
    obj = module
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


def object_hook(d: dict):
    class_spec = d.get(".type")
    if class_spec is None:
        return d
    payload = dict(d)
    payload.pop(".type")
    cls = _load_class(class_spec=class_spec)
    return cls.__deserialize__(payload)


def dump(*args, **kwargs):
    return json.dump(*args, cls=Encoder, **kwargs)


def dumps(*args, **kwargs):
    return json.dumps(*args, cls=Encoder, **kwargs)


def dumps_min(*args, **kwargs):
    return json.dumps(*args, cls=Encoder, separators=(",", ":"), **kwargs)


def load(*args, **kwargs):
    return json.load(*args, object_hook=object_hook, **kwargs)


def loads(*args, **kwargs):
    return json.loads(*args, object_hook=object_hook, **kwargs)


def safesave(file: str, state: dict[str, Any]) -> None:
    dirname, basename = os.path.split(file)
    tmp = os.path.join(dirname, f".{basename}.tmp")
    mkdirp(dirname)
    try:
        with open(tmp, "w") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp, file)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def safeload(file: str, attempts: int = 8) -> dict[str, Any]:
    delay = 0.5
    attempt = 0
    while attempt <= attempts:
        # Guard against race condition when multiple batches are running at once
        attempt += 1
        try:
            with open(file, "r") as fh:
                return load(fh)
        except Exception:
            time.sleep(delay)
            delay *= 2
    raise FailedToLoadError(
        f"Failed to load {file} after {attempts} {pluralize('attempt', attempts)}"
    )


def try_loads(arg):
    """Attempt to deserialize ``arg`` into a python object. If the deserialization fails,
    return ``arg`` unmodified.

    """
    try:
        return loads(arg)
    except json.decoder.JSONDecodeError:
        return arg


class FailedToLoadError(Exception):
    pass
