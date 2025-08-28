import json
import os
import time
from typing import Any

from .filesystem import mkdirp
from .string import pluralize


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
