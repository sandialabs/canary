# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Helpers for loading Canary query data from package resources."""

import json
from importlib import resources
from typing import Any


def load_query_data(package: str, filename: str) -> dict[str, Any] | None:
    """Load a JSON query-data resource from an importable package.

    Args:
        package: Importable package containing the JSON resource, e.g.
            ``"canary_pyt.data"`` or ``"canary.data"``.
        filename: JSON resource filename, e.g. ``"capabilities.json"`` or
            ``"skills.json"``.

    Returns:
        Parsed JSON object, or ``None`` if the resource does not exist.

    Notes:
        This helper assumes ``package`` is importable. For extension query data,
        prefer using a package such as ``canary_pyt.data`` rather than manually
        joining a ``data`` directory below ``canary_pyt``.
    """
    root = resources.files(package)
    path = root.joinpath(filename)

    if not path.is_file():
        return None

    return json.loads(path.read_text(encoding="utf-8"))


def require_query_data(package: str, filename: str) -> dict[str, Any]:
    """Load a required JSON query-data resource from an importable package."""
    data = load_query_data(package, filename)
    if data is None:
        raise FileNotFoundError(f"{package}:{filename}")
    return data
