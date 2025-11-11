import json
import os
import time
from pathlib import Path
from typing import Any

from .filesystem import mkdirp
from .string import pluralize


class PathEncoder(json.JSONEncoder):

    def default(self, obj):
        from ..paramset import ParameterSet

        if isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, ParameterSet):
            return {"keys": obj.keys, "values": obj.values}
        return json.JSONEncoder.default(self, obj)


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


class FailedToLoadError(Exception):
    pass
