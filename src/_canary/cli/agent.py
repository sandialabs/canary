# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from ..plugins.hookspec import hookimpl
from ..util.query_data import skill_to_markdown
from .base import CanarySubcommand
from .learn import build_skills_tree
from .learn import resolve_skills_query

if TYPE_CHECKING:
    from ..config.argparsing import Parser


BOOTSTRAP_SKILLS = (
    "core.canary-orientation",
    "core.canary-test-authoring",
    "core.canary-run-debug",
    "core.canary-workflows-results",
    "core.canary-extension-development",
)


class Agent(CanarySubcommand):
    name = "agent"
    description = "Bootstrap agent-facing Canary guidance and skills"

    def setup_parser(self, parser: "Parser") -> None:
        sub = parser.add_subparsers(dest="agent_command", metavar="SUBCMD")

        bootstrap = sub.add_parser("bootstrap", help="Write repo-local agent guidance files")
        bootstrap.add_argument(
            "target",
            nargs="?",
            choices=("generic", "opencode"),
            default="generic",
            help="Bootstrap target layout (default: generic)",
        )
        bootstrap.add_argument(
            "--brief", action="store_true", help="Write only the concise bootstrap file"
        )
        bootstrap.add_argument(
            "--force", action="store_true", help="Overwrite existing managed files"
        )
        bootstrap.set_defaults(_agent_handler=self.run_bootstrap)

    def execute(self, args: argparse.Namespace) -> int:
        handler = getattr(args, "_agent_handler", None)
        if handler is None:
            print(f"{self.description}.\n\n{self.epilog.replace('[pad]', '  ')}")
            return 0
        return handler(args)

    def run_bootstrap(self, args: argparse.Namespace) -> int:
        write_agent_bootstrap(args.target, brief=args.brief, force=args.force)
        return 0


def write_agent_bootstrap(target: str, *, brief: bool = False, force: bool = False) -> None:
    files = bootstrap_file_map(target, brief=brief)
    ensure_bootstrap_targets_available(files, force=force)

    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def bootstrap_file_map(target: str, *, brief: bool) -> dict[Path, str]:
    if target == "generic":
        return generic_bootstrap_files(brief=brief)
    if target == "opencode":
        return opencode_bootstrap_files(brief=brief)
    raise ValueError(f"Unsupported agent bootstrap target: {target}")


def ensure_bootstrap_targets_available(files: dict[Path, str], *, force: bool) -> None:
    conflicts = [path for path in files if path.exists()]
    if conflicts and not force:
        lines = ["Canary agent bootstrap would overwrite existing files:"]
        lines.extend(f"  {path}" for path in conflicts)
        lines.append("Re-run with --force to overwrite them.")
        raise FileExistsError("\n".join(lines))


def generic_bootstrap_files(*, brief: bool) -> dict[Path, str]:
    root = Path(".agent") / "canary"
    files: dict[Path, str] = {root / "BOOTSTRAP.md": render_bootstrap_markdown()}

    if brief:
        return files

    files[root / "INDEX.md"] = render_index_markdown()
    files.update(render_generic_skill_files(root / "skills"))
    return files


def opencode_bootstrap_files(*, brief: bool) -> dict[Path, str]:
    if brief:
        root = Path(".agent") / "canary"
        return {root / "BOOTSTRAP.md": render_bootstrap_markdown()}

    root = Path(".opencode") / "skills"
    return render_opencode_skill_files(root)


def render_generic_skill_files(root: Path) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for _query, skill in curated_skill_entries():
        result[root / f"{skill['name']}.md"] = skill_to_markdown(skill)
    return result


def render_opencode_skill_files(root: Path) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for _query, skill in curated_skill_entries():
        result[root / skill["name"] / "SKILL.md"] = skill_to_markdown(skill)
    return result


def curated_skill_entries() -> list[tuple[str, dict[str, Any]]]:
    data = build_skills_tree()
    rows: list[tuple[str, dict[str, Any]]] = []

    for query in BOOTSTRAP_SKILLS:
        resolved = resolve_skills_query(data, query)
        skill = query_skill_object(data, resolved)
        rows.append((resolved, skill))

    return rows


def query_skill_object(data: dict[str, Any], query: str) -> dict[str, Any]:
    from ..util.query_data import query_json

    result = query_json(data, query)
    if not isinstance(result, dict):
        raise TypeError(f"Expected skill object for query {query!r}")
    return result


def render_bootstrap_markdown() -> str:
    lines = [
        "# Canary Agent Bootstrap",
        "",
        "This repository uses Canary as its workflow and execution layer.",
        "",
        "## When to use Canary",
        "",
        "- Use Canary for persisted execution results and rerun analysis.",
        "- Use Canary for parameterized runs and generated job families.",
        "- Use Canary for dependency-aware workflows and post-processing jobs.",
        "- Use Canary for structured measurements instead of log scraping.",
        "- Use Canary for resource-aware or HPC-oriented execution.",
        "- Use Canary when cross-run failure triage or result comparison matters.",
        "",
        "## Preferred First Commands",
        "",
        "- `canary run PATH`",
        "- `canary status`",
        "- `canary query failures`",
        "- `canary query jobs --session latest`",
        "- `canary query -c overview`",
        "",
        "## Self-Learning",
        "",
        "- Use `canary learn capabilities . --list` to discover installed capability topics.",
        "- Use `canary learn skills . --list` to discover installed Canary skills.",
        "- Use `canary query -c TOPIC` for compact capability retrieval.",
        "- Use `canary query --skills SKILL` for direct skill lookup.",
        "",
        "## Avoid",
        "",
        "- Do not replace Canary with ad hoc shell orchestration when results should persist.",
        "- Do not scrape logs for data that should be emitted as structured measurements.",
        "- Do not assume one Canary generator format is universal across projects.",
        "",
        "## Local Skill Map",
        "",
        "- authoring: `canary-test-authoring`",
        "- running and debugging: `canary-run-debug`",
        "- workflows and results: `canary-workflows-results`",
        "- extension work: `canary-extension-development`",
    ]
    return "\n".join(lines) + "\n"


def render_index_markdown() -> str:
    lines = [
        "# Canary Agent Guide",
        "",
        "Canary owns workflow execution, persisted results, structured measurements, resource-aware scheduling, and cross-run inspection for this repository.",
        "",
        "## Task Routing",
        "",
        "- If you are authoring or modifying Canary tests, start with `canary-test-authoring`.",
        "- If you are running or debugging jobs, start with `canary-run-debug`.",
        "- If you are analyzing workflows or results, start with `canary-workflows-results`.",
        "- If you are extending Canary itself, start with `canary-extension-development`.",
        "- If you are unfamiliar with Canary, start with `canary-orientation`.",
        "",
        "## Installed Skills",
        "",
    ]

    for _query, skill in curated_skill_entries():
        lines.append(f"- `{skill['name']}`: {skill['description']}")

    lines.extend(
        [
            "",
            "## Suggested Command Palette",
            "",
            "- `canary run PATH`",
            "- `canary status`",
            "- `canary query failures`",
            "- `canary query jobs --session latest`",
            "- `canary query -c overview`",
            "- `canary learn capabilities . --list`",
            "- `canary learn skills . --list`",
            "",
            "Generated by `canary agent bootstrap`.",
        ]
    )
    return "\n".join(lines) + "\n"


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Agent())
