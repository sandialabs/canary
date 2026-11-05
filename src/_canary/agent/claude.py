# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path

from ..util.query_data import skill_to_markdown
from .common import curated_skill_entries
from .common import render_core_bootstrap_skills
from .common import render_skill_map
from .common import render_template

CLAUDE_GUIDANCE_PATH = Path("CLAUDE.md")
CLAUDE_CANARY_BEGIN = "<!-- BEGIN CANARY GUIDANCE -->"
CLAUDE_CANARY_END = "<!-- END CANARY GUIDANCE -->"


def claude_bootstrap_files(*, brief: bool) -> dict[Path, str]:
    files: dict[Path, str] = {CLAUDE_GUIDANCE_PATH: render_claude_guidance_markdown()}

    if brief:
        return files

    root = Path(".claude") / "skills"
    files.update(render_claude_skill_files(root))
    return files


def render_claude_skill_files(root: Path) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for _query, skill in curated_skill_entries():
        result[root / skill["name"] / "SKILL.md"] = skill_to_markdown(skill)
    return result


def append_or_refresh_claude_guidance(path: Path, guidance: str) -> None:
    if not path.exists():
        path.write_text(guidance, encoding="utf-8")
        return

    existing = path.read_text(encoding="utf-8")
    start = existing.find(CLAUDE_CANARY_BEGIN)
    end = existing.find(CLAUDE_CANARY_END)

    if start != -1 and end != -1 and start < end:
        block_end = end + len(CLAUDE_CANARY_END)
        while block_end < len(existing) and existing[block_end] in " \t":
            block_end += 1
        if block_end < len(existing) and existing[block_end] == "\n":
            block_end += 1
        updated = existing[:start] + guidance + existing[block_end:]
    else:
        separator = "" if existing.endswith("\n") else "\n"
        updated = f"{existing}{separator}\n{guidance}"

    path.write_text(updated, encoding="utf-8")


def render_claude_guidance_markdown() -> str:
    return render_template(
        "claude.md.in",
        {"CORE_BOOTSTRAP_SKILLS": render_core_bootstrap_skills(), "SKILL_MAP": render_skill_map()},
    )
