# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
"""Parsing of scheduler wall-time limits supplied in submit arguments.

There is exactly one parser for user-pinned wall limits so that the value used
to size/enforce a batch (``TestBatch.wall_limit``) and the value used for
diagnostics can never disagree.
"""

import re
import shlex
from typing import Sequence

#: Flags that pin a scheduler wall limit (Slurm ``--time``/``-t``, Flux/canary
#: ``--time-limit``).
WALL_TIME_FLAGS = ("--time-limit", "--time", "-t")

_UNIT_SECONDS = {
    "s": 1.0,
    "sec": 1.0,
    "secs": 1.0,
    "m": 60.0,
    "min": 60.0,
    "mins": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hrs": 3600.0,
    "d": 86400.0,
    "day": 86400.0,
    "days": 86400.0,
}
_NUM = r"(?:\d+(?:\.\d*)?|\.\d+)"
_SUFFIXED = re.compile(rf"(?i)^\s*({_NUM})\s*([a-z]+)\s*$")
_COMPOUND = re.compile(rf"(?i)({_NUM})\s*([a-z]+)")


class WallTimeError(ValueError):
    """Raised when a pinned wall time cannot be parsed or is not positive."""


def parse_wall_time(value: str, *, bare_unit: float = 60.0) -> float:
    """Parse a scheduler wall-time string into seconds.

    Accepted forms:

    * Slurm: ``MM``, ``MM:SS``, ``HH:MM:SS``, ``D-HH``, ``D-HH:MM``, ``D-HH:MM:SS``.
    * A bare number is multiplied by *bare_unit*: minutes for Slurm ``--time``
      (the default), seconds for Flux ``--time-limit`` (Flux standard duration).
    * Unit-suffixed: ``90s``, ``30m``, ``1.5h``, ``2d`` and compounds such as
      ``1h30m`` (Flux FSD / Go-style durations).
    * ``INFINITE``/``UNLIMITED`` are rejected: canary cannot size a batch from them.

    Raises:
        WallTimeError: If *value* is malformed or does not denote a positive duration.
    """
    original = value
    text = str(value).strip().strip("'\"").strip()
    if not text:
        raise WallTimeError(f"Empty wall time {original!r}")
    if text.lower() in ("infinite", "unlimited"):
        raise WallTimeError(f"Unbounded wall time {original!r} cannot be used to size a batch")

    seconds: float | None = None
    if m := _SUFFIXED.match(text):
        unit = m.group(2).lower()
        if unit in _UNIT_SECONDS:
            seconds = float(m.group(1)) * _UNIT_SECONDS[unit]
    if seconds is None and re.fullmatch(rf"(?i)(?:\s*{_NUM}\s*[a-z]+)+\s*", text):
        total = 0.0
        for num, unit in _COMPOUND.findall(text):
            unit = unit.lower()
            if unit not in _UNIT_SECONDS:
                raise WallTimeError(f"Unknown unit {unit!r} in wall time {original!r}")
            total += float(num) * _UNIT_SECONDS[unit]
        seconds = total
    if seconds is None and re.fullmatch(_NUM, text):
        seconds = float(text) * bare_unit
    if seconds is None:
        seconds = _parse_slurm(text, original)
    if not seconds > 0:
        raise WallTimeError(f"Wall time {original!r} must be greater than zero")
    return seconds


def _parse_slurm(text: str, original: str) -> float:
    days = 0
    body = text
    has_days = False
    if "-" in body:
        d, _, body = body.partition("-")
        if not d.isdigit() or not body:
            raise WallTimeError(f"Invalid wall time {original!r}")
        days = int(d)
        has_days = True
    parts = body.split(":")
    if not all(p.isdigit() for p in parts) or not 1 <= len(parts) <= 3:
        raise WallTimeError(f"Invalid wall time {original!r}")
    nums = [int(p) for p in parts]
    if has_days:
        # D-HH, D-HH:MM, D-HH:MM:SS
        hh, mm, ss = (nums + [0, 0])[:3]
        if hh >= 24 or mm >= 60 or ss >= 60:
            raise WallTimeError(f"Invalid wall time {original!r}: field out of range")
    elif len(nums) == 1:
        hh, mm, ss = 0, nums[0], 0  # MM (may exceed 59, as in Slurm)
    elif len(nums) == 2:
        hh, mm, ss = 0, nums[0], nums[1]  # MM:SS (minutes may exceed 59)
        if ss >= 60:
            raise WallTimeError(f"Invalid wall time {original!r}: field out of range")
    else:
        hh, mm, ss = nums  # HH:MM:SS (hours may exceed 23)
        if mm >= 60 or ss >= 60:
            raise WallTimeError(f"Invalid wall time {original!r}: field out of range")
    return days * 86400.0 + hh * 3600.0 + mm * 60.0 + ss


def find_wall_time_arg(submit_args: Sequence[str] | None) -> tuple[str, str] | None:
    """Return ``(flag, value)`` for the *last* wall-time flag in *submit_args*, if any.

    The last occurrence wins so that command-line options (appended after
    per-batch options) take precedence, matching scheduler behaviour.
    """
    if not submit_args:
        return None
    tokens: list[str] = []
    for arg in submit_args:
        if isinstance(arg, str):
            try:
                tokens.extend(shlex.split(arg))
            except ValueError:
                tokens.append(arg)
        else:
            tokens.append(str(arg))
    found: tuple[str, str] | None = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        for key in WALL_TIME_FLAGS:
            if tok == key:
                if i + 1 < len(tokens):
                    found = (key, tokens[i + 1])
                    i += 1
                break
            if tok.startswith(key + "="):
                found = (key, tok.split("=", 1)[1])
                break
            if key == "-t" and tok.startswith("-t") and not tok.startswith("--") and len(tok) > 2:
                found = (key, tok[2:])  # -t30:00
                break
        i += 1
    return found


def pinned_wall_seconds(submit_args: Sequence[str] | None) -> float | None:
    """Return the user-pinned wall limit (seconds) in *submit_args*, or ``None``.

    Raises:
        WallTimeError: If a wall-time flag is present but its value is invalid.
            A pinned value is never silently ignored or misread.
    """
    found = find_wall_time_arg(submit_args)
    if found is None:
        return None
    flag, value = found
    try:
        return parse_wall_time(value, bare_unit=1.0 if flag == "--time-limit" else 60.0)
    except WallTimeError as e:
        raise WallTimeError(f"Invalid scheduler wall time in submit arguments: {e}") from None
