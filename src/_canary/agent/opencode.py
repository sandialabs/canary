# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from ..util.query_data import skill_to_markdown
from .common import curated_skill_entries
from .common import generic_bootstrap_files
from .common import render_bootstrap_markdown


def opencode_bootstrap_files(*, brief: bool) -> dict[Path, str]:
    if brief:
        root = Path(".agent") / "canary"
        return {root / "BOOTSTRAP.md": render_bootstrap_markdown()}

    files = generic_bootstrap_files(brief=False)
    root = Path(".opencode") / "skills"
    files.update(render_opencode_skill_files(root))
    return files


def render_opencode_skill_files(root: Path) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for _query, skill in curated_skill_entries():
        result[root / skill["name"] / "SKILL.md"] = skill_to_markdown(skill)
    return result
