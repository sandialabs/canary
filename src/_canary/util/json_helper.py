# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import json.decoder
import os
import time
from pathlib import Path
from typing import Any

from .filesystem import mkdirp
from .string import pluralize


class PathEncoder(json.JSONEncoder):
    def default(self, o):
        from ..paramset import ParameterSet

        if isinstance(o, Path):
            return str(o)
        elif isinstance(o, ParameterSet):
            return {"keys": o.keys, "values": o.values}
        return json.JSONEncoder.default(self, o)


def dump(*args, **kwargs):
    return json.dump(*args, cls=PathEncoder, **kwargs)


def dumps(*args, **kwargs):
    return json.dumps(*args, cls=PathEncoder, **kwargs)


def dumps_min(*args, **kwargs):
    return json.dumps(*args, cls=PathEncoder, separators=(",", ":"), **kwargs)


def load(*args, **kwargs):
    return json.load(*args, **kwargs)


def loads(*args, **kwargs):
    return json.loads(*args, **kwargs)


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
                return json.load(fh)
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
        return json.loads(arg)
    except json.decoder.JSONDecodeError:
        return arg


class FailedToLoadError(Exception):
    pass
