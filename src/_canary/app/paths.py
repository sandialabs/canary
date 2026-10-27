# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path


def remap_path(path: str | Path, *, root_at_creation: str | None, current_root: str | Path) -> str:
    text = str(path)
    if not root_at_creation:
        return text
    current = str(Path(current_root))
    if text.startswith(root_at_creation):
        return current + text[len(root_at_creation) :]
    return text
