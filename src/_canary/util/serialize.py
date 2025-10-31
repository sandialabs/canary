import json
import pickle  # nosec B403
import time
from pathlib import Path
from typing import Any

from .string import pluralize

PICKLE = 0
JSON = 1

protocol = JSON


def dump(file: str | Path, obj: Any) -> None:
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".tmp")
    if protocol == JSON:
        with open(tmp, "w") as fh:
            json.dump(obj, fh, indent=2)
    else:
        with open(tmp, "wb") as fh:
            pickle.dump(obj, fh)  # nosec B301
    tmp.replace(file)


def load(file: str | Path, attempts: int = 8) -> Any:
    file = Path(file)
    delay = 0.5
    attempt = 0
    while attempt <= attempts:
        # Guard against race condition when multiple batches are running at once
        attempt += 1
        try:
            if protocol == JSON:
                with open(file, "r") as fh:
                    return json.load(fh)
            else:
                with open(file, "rb") as fh:
                    return pickle.load(fh)  # nosec B301
        except Exception:
            time.sleep(delay)
            delay *= 2
    raise FailedToLoadError(
        f"Failed to load {file.name} after {attempts} {pluralize('attempt', attempts)}"
    )


class FailedToLoadError(Exception):
    pass
