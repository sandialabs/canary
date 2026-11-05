# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import re
from importlib import resources
from pathlib import Path
from typing import Any

from ..util.query_data import iter_skill_objects
from ..util.query_data import skill_to_markdown

CORE_BOOTSTRAP_SKILLS = (
    "canary-test-authoring",
    "canary-run-debug",
    "canary-workflows-results",
    "canary-extension-development",
)

_TEMPLATE_TOKEN_RE = re.compile(r"@@[A-Z0-9_]+@@")


def curated_skill_entries() -> list[tuple[str, dict[str, Any]]]:
    from ..cli.learn import build_skills_tree

    data = build_skills_tree()
    return sorted(iter_skill_objects(data), key=lambda item: item[0])


def render_generic_skill_files(root: Path) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for _query, skill in curated_skill_entries():
        result[root / f"{skill['name']}.md"] = skill_to_markdown(skill)
    return result


def generic_bootstrap_files(*, brief: bool) -> dict[Path, str]:
    root = Path(".agent") / "canary"
    files: dict[Path, str] = {root / "BOOTSTRAP.md": render_bootstrap_markdown()}

    if brief:
        return files

    files[root / "INDEX.md"] = render_index_markdown()
    files.update(render_generic_skill_files(root / "skills"))
    return files


def can_refresh_managed_file(path: Path, new_text: str) -> bool:
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError:
        return False

    if existing == new_text:
        return True

    if path.name == "BOOTSTRAP.md":
        return existing.startswith("# Canary Agent Bootstrap\n")

    if path.name == "INDEX.md":
        return existing.startswith("# Canary Agent Guide\n")

    expected_name = extract_skill_name(new_text)
    if expected_name is None:
        return False

    return extract_skill_name(existing) == expected_name


def extract_skill_name(text: str) -> str | None:
    match = re.search(r"^name:\s+(.+)$", text, flags=re.MULTILINE)
    if match is None:
        return None
    return match.group(1).strip()


def render_template(name: str, replacements: dict[str, str]) -> str:
    template = (
        resources.files("canary.data").joinpath("agent").joinpath(name).read_text(encoding="utf-8")
    )
    for key, value in replacements.items():
        template = template.replace(f"@@{key}@@", value)

    remaining = sorted(set(_TEMPLATE_TOKEN_RE.findall(template)))
    if remaining:
        tokens = ", ".join(remaining)
        raise ValueError(f"Unresolved agent template token(s) in {name}: {tokens}")

    if not template.endswith("\n"):
        template += "\n"
    return template


def render_skill_map() -> str:
    return "\n".join(
        f"- `{skill['name']}`: {skill['description']}" for _query, skill in curated_skill_entries()
    )


def render_core_bootstrap_skills() -> str:
    return "\n".join(f"- `{name}`" for name in CORE_BOOTSTRAP_SKILLS)


def render_bootstrap_markdown() -> str:
    return render_template(
        "generic-bootstrap.md.in",
        {"SKILL_MAP": render_skill_map(), "CORE_BOOTSTRAP_SKILLS": render_core_bootstrap_skills()},
    )


def render_index_markdown() -> str:
    return render_template("generic-index.md.in", {"SKILL_MAP": render_skill_map()})
