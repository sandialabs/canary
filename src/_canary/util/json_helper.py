# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""JSON encoding/decoding helpers with custom type support and safe I/O.

Provides ``Encoder`` (handles ``Path``, ``tuple``, and ``__serialize__``
objects), ``object_hook`` for deserialization, and higher-level helpers
``safesave``/``safeload`` for atomic file I/O and race-condition resilience.
"""

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
    """Custom JSON encoder that handles ``Path``, ``tuple``, and ``__serialize__`` objects.

    Objects with a ``__serialize__`` method are encoded as dicts with a
    ``__type__`` key so they can be reconstructed by ``object_hook``.
    """

    def default(self, o: Any):
        """Encode non-standard types to JSON-safe values.

        Args:
            o: Object to encode.

        Returns:
            A JSON-serializable representation of ``o``.
        """
        if isinstance(o, Path):
            return str(o.as_posix())
        elif isinstance(o, tuple):
            return list(o)
        elif hasattr(o, "__serialize__"):
            serialized = o.__serialize__()
            # If __serialize__ returns a plain scalar (str, int, etc.) emit it directly
            # without wrapping in a __type__ envelope.
            if not isinstance(serialized, dict):
                return serialized
            data = dict(serialized)
            data["__type__"] = f"{o.__class__.__module__}::{o.__class__.__qualname__}"
            return data
        return json.JSONEncoder.default(self, o)


def _load_class(class_spec: str) -> Any:
    """Import and return a class given a ``module::QualName`` specifier."""
    modulename, qualname = class_spec.split("::")
    module = importlib.import_module(modulename)
    obj = module
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


def object_hook(d: dict):
    """Reconstruct typed objects from JSON dicts that contain a ``__type__`` key.

    Args:
        d: Raw decoded dict from the JSON parser.

    Returns:
        The original typed object if ``__type__`` is present, otherwise ``d``.
    """
    class_spec = d.get("__type__")
    if class_spec is None:
        return d
    payload = dict(d)
    payload.pop("__type__")
    cls = _load_class(class_spec=class_spec)
    return cls.__deserialize__(payload)


def dump(*args, **kwargs):
    """Serialize ``obj`` to a JSON-formatted stream using ``Encoder``.

    Forwards all arguments to :func:`json.dump` with ``cls=Encoder``.
    """
    return json.dump(*args, cls=Encoder, **kwargs)


def dumps(*args, **kwargs):
    """Serialize ``obj`` to a JSON-formatted string using ``Encoder``.

    Forwards all arguments to :func:`json.dumps` with ``cls=Encoder``.
    """
    return json.dumps(*args, cls=Encoder, **kwargs)


def dumps_min(*args, **kwargs):
    """Serialize ``obj`` to a compact (no whitespace) JSON string using ``Encoder``.

    Forwards all arguments to :func:`json.dumps` with minimal separators.
    """
    return json.dumps(*args, cls=Encoder, separators=(",", ":"), **kwargs)


def load(*args, **kwargs):
    """Deserialize JSON from a stream, reconstructing typed objects via ``object_hook``.

    Forwards all arguments to :func:`json.load`.
    """
    return json.load(*args, object_hook=object_hook, **kwargs)


def loads(*args, **kwargs):
    """Deserialize JSON from a string, reconstructing typed objects via ``object_hook``.

    Forwards all arguments to :func:`json.loads`.
    """
    return json.loads(*args, object_hook=object_hook, **kwargs)


def safesave(file: str | os.PathLike[str], state: Any, *, indent: int | None = 2) -> None:
    """Atomically write ``state`` as JSON to ``file``.

    Writes to a temporary sibling file first, then renames it into place to
    avoid partial writes.

    Args:
        file: Destination file path.
        state: JSON-serializable object to write.
        indent: Indentation level passed to :func:`dump`; default 2.
    """
    path = os.fspath(file)
    dirname, basename = os.path.split(path)
    tmp = os.path.join(dirname, f".{basename}.tmp")

    mkdirp(dirname)

    try:
        with open(tmp, "w") as fh:
            dump(state, fh, indent=indent)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def safeload(file: str, attempts: int = 8) -> dict[str, Any]:
    """Load a JSON file with retries to guard against concurrent write races.

    Retries up to ``attempts`` times with exponential back-off.

    Args:
        file: Path to the JSON file to load.
        attempts: Maximum number of read attempts before raising.

    Returns:
        Parsed JSON object.

    Raises:
        FailedToLoadError: If all attempts fail.
    """
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
    """Raised when ``safeload`` exhausts all retry attempts."""

    pass
