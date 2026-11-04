# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Plugin specification normalization helpers.

Stage 1 introduces a session-only plugin representation shared by bootstrap
loading and config snapshots.  A plugin spec always names the import target and
may optionally include a directory to prepend to ``sys.path`` before import.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def plugin_spec_schema() -> dict[str, Any]:
    return {"name": str, "path": str}


def parse_env_plugins(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def derive_import_name(raw: str) -> str:
    path = Path(raw)
    if raw.endswith(".py"):
        return path.stem
    return path.name


def normalize_plugin_spec(
    raw: str, *, base: str | os.PathLike[str] | None = None
) -> dict[str, str]:
    """Normalize a raw CLI/env plugin token into ``name``/``path`` form.

    Rules:
      - dotted module names become ``{"name": raw}``
      - ``/x/y/mod.py`` becomes ``{"name": "mod", "path": "/x/y"}``
      - ``/x/y/pkg`` becomes ``{"name": "pkg", "path": "/x/y"}``
    """

    if not isinstance(raw, str):
        raise TypeError(f"plugin spec must be text, got {type(raw).__name__}")

    candidate = raw.strip()
    if not candidate:
        raise ValueError("plugin spec must not be empty")

    resolved = (
        os.path.abspath(os.path.join(str(base), candidate))
        if base is not None and not os.path.isabs(candidate)
        else os.path.abspath(candidate)
    )

    if candidate.endswith(".py") or os.path.isfile(resolved):
        parent = os.path.dirname(resolved)
        return {"name": Path(resolved).stem, "path": parent}

    if os.path.isdir(resolved):
        init = os.path.join(resolved, "__init__.py")
        if not os.path.isfile(init):
            raise ImportError(
                f"Plugin directory {candidate!r} does not contain an __init__.py; "
                "it cannot be imported as a package."
            )
        return {"name": os.path.basename(resolved), "path": os.path.dirname(resolved)}

    return {"name": candidate}


def normalize_plugin_specs(
    items: list[str] | None, *, base: str | os.PathLike[str] | None = None
) -> list[dict[str, str]]:
    return [normalize_plugin_spec(item, base=base) for item in (items or [])]


def plugin_display_name(spec: dict[str, str]) -> str:
    path = spec.get("path")
    if path:
        return os.path.join(path, spec["name"])
    return spec["name"]
