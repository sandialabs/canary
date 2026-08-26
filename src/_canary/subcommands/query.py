# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Iterator

import yaml

from .. import config
from ..config.schemas import core_capabilities_schema
from ..config.schemas import core_skills_schema
from ..config.schemas import extension_capabilities_schema
from ..config.schemas import extension_skills_schema
from ..hookspec import hookimpl
from ..util.query_data import require_query_data
from ..workspace import Workspace
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


CAPABILITIES_RESOURCE = "capabilities.json"
SKILLS_RESOURCE = "skills.json"
CAPABILITY_HELP_QUERY = "__canary_capability_help__"
SKILL_HELP_QUERY = "__canary_skill_help__"


class Query(CanarySubcommand):
    name = "query"
    description = "Query Canary job/session lock files or capability/skill data"

    def setup_parser(self, parser: "Parser") -> None:
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "-j", "--job", dest="jobid", metavar="JOBID", help="Query the testcase.lock for JOBID"
        )
        group.add_argument(
            "-s",
            "--session",
            dest="session",
            metavar="SESSION",
            help="Query the session.lock for SESSION",
        )
        group.add_argument(
            "-c",
            "--capability",
            dest="capability",
            metavar="QUERY",
            nargs="?",
            const=CAPABILITY_HELP_QUERY,
            help=(
                "Query Canary's aggregated capability tree. "
                "Examples: '.', 'overview', 'hooks.post', 'ext.pyt.overview'. "
                "If QUERY is omitted, print query guidance."
            ),
        )
        group.add_argument(
            "-k",
            "--skill",
            dest="skill",
            metavar="QUERY",
            nargs="?",
            const=SKILL_HELP_QUERY,
            help=(
                "Query Canary's aggregated skill tree. "
                "Examples: '.', 'canary-orientation', 'ext.pyt.canary-pyt-authoring'. "
                "If QUERY is omitted, print query guidance."
            ),
        )
        parser.add_argument("--terse", action="store_true", help="Print compact single-line JSON")
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_keys",
            help="List queryable keys below the selected query point",
        )
        parser.add_argument(
            "-m",
            "--markdown",
            metavar="PATH",
            help=(
                "Write selected skill or skill subtree as Markdown. "
                "For a single skill, PATH is a Markdown file or an existing directory. "
                "For a skill subtree, PATH is an output directory."
            ),
        )
        parser.add_argument(
            "query",
            nargs="?",
            default=".",
            help=(
                "Query expression for job/session queries. "
                "For capability and skill queries, put the query in -c/--capability "
                "or -k/--skill."
            ),
        )

    def execute(self, args: argparse.Namespace) -> int:
        if args.capability is not None:
            if args.query != ".":
                raise ValueError(
                    "Capability queries must be supplied directly to -c/--capability. "
                    "For example: canary query -c ext.pyt.overview"
                )
            if args.markdown:
                raise ValueError("--markdown is only valid with --skill")
            capability_query = args.capability
            if capability_query == CAPABILITY_HELP_QUERY:
                if args.list_keys:
                    capability_query = "."
                else:
                    print_capability_query_help()
                    return 0
            data = build_capabilities_tree()
            if args.list_keys:
                print_query_paths(list_capability_paths(data, capability_query))
                return 0
            data = query_json(data, capability_query)

        elif args.skill is not None:
            if args.query != ".":
                raise ValueError(
                    "Skill queries must be supplied directly to -k/--skill. "
                    "For example: canary query --skill ext.pyt.canary-pyt-authoring"
                )

            skill_query = args.skill

            if skill_query == SKILL_HELP_QUERY:
                if args.list_keys:
                    skill_query = "."
                else:
                    print_skill_query_help()
                    return 0

            data = build_skills_tree()

            if args.list_keys:
                print_query_paths(list_skill_paths(data, skill_query))
                return 0

            data = query_json(data, skill_query)

            if args.markdown:
                write_skill_markdown(skill_query, data, Path(args.markdown))
                return 0

        else:
            if args.markdown:
                raise ValueError("--markdown is only valid with --skill")

            workspace = Workspace.load()
            if args.jobid:
                lockfile = self.job_lockfile(workspace, args.jobid)
            else:
                lockfile = self.session_lockfile(workspace, args.session)

            data = json.loads(lockfile.read_text())

            if args.list_keys:
                print_query_paths(list_json_object_paths(data, args.query))
                return 0

            data = query_json(data, args.query)

        if args.terse:
            json.dump(data, sys.stdout, separators=(",", ":"))
        else:
            json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    def job_lockfile(self, workspace: Workspace, jobid: str) -> Path:
        job = workspace.find_job(jobid)
        lockfile = job.lockfile
        if not lockfile.exists():
            raise FileNotFoundError(lockfile)
        return lockfile

    def session_lockfile(self, workspace: Workspace, session: str) -> Path:
        session_dir = self.resolve_session_dir(workspace, session)
        lockfile = session_dir / "session.lock"
        if not lockfile.exists():
            raise FileNotFoundError(lockfile)
        return lockfile

    def resolve_session_dir(self, workspace: Workspace, session: str) -> Path:
        if session == "latest":
            latest = workspace.refs_dir / "latest"
            if not latest.exists():
                raise FileNotFoundError(latest)
            rel = latest.read_text().strip()
            return (workspace.refs_dir / rel).resolve()

        candidate = workspace.sessions_dir / session
        if candidate.is_dir():
            return candidate

        matches = sorted(p for p in workspace.sessions_dir.glob(f"{session}*") if p.is_dir())

        if not matches:
            raise ValueError(f"{session!r}: no matching session found")

        if len(matches) > 1:
            names = ", ".join(p.name for p in matches[:8])
            if len(matches) > 8:
                names += ", ..."
            raise ValueError(f"{session!r}: ambiguous session prefix; matches: {names}")

        return matches[0]


# -------------------------------------------------------------------------
# Capability / skill loading and aggregation
# -------------------------------------------------------------------------


def load_core_capabilities_document() -> dict[str, Any]:
    """Load and validate Canary core capabilities."""
    try:
        data = require_query_data("canary.data", CAPABILITIES_RESOURCE)
    except FileNotFoundError as e:
        raise CapabilityDatasetNotFoundError("canary.data:capabilities.json") from e

    return core_capabilities_schema.validate(data)


def load_core_skills_document() -> dict[str, Any]:
    """Load and validate Canary core skills."""
    try:
        data = require_query_data("canary.data", SKILLS_RESOURCE)
    except FileNotFoundError as e:
        raise SkillDatasetNotFoundError("canary.data:skills.json") from e

    return core_skills_schema.validate(data)


def build_capabilities_tree() -> dict[str, Any]:
    """Build the runtime aggregate capabilities tree.

    Core capabilities are loaded from package data. Extension capabilities are
    supplied by plugins through ``canary_capabilities`` and inserted under
    ``ext.<extension>``.
    """
    document = load_core_capabilities_document()
    tree: dict[str, Any] = dict(document["capabilities"])

    ext_tree = tree.setdefault("ext", {})
    if not isinstance(ext_tree, dict):
        raise TypeError("Core capabilities key 'ext' is reserved and must be an object")

    payloads = config.pluginmanager.hook.canary_capabilities()

    for payload in payloads:
        if payload is None:
            continue

        ext_name, ext_payload = normalize_extension_capabilities(payload)

        if ext_name in ext_tree:
            raise ValueError(f"Duplicate Canary capabilities extension namespace: {ext_name}")

        ext_tree[ext_name] = ext_payload

    return tree


def build_skills_tree() -> dict[str, Any]:
    """Build the runtime aggregate skills tree.

    Core skills are loaded from package data. Extension skills are supplied by
    plugins through ``canary_skills`` and inserted under ``ext.<extension>``.
    """
    document = load_core_skills_document()
    tree: dict[str, Any] = dict(document["skills"])

    ext_tree = tree.setdefault("ext", {})
    if not isinstance(ext_tree, dict):
        raise TypeError("Core skills key 'ext' is reserved and must be an object")

    payloads = config.pluginmanager.hook.canary_skills()

    for payload in payloads:
        if payload is None:
            continue

        ext_name, ext_payload = normalize_extension_skills(payload)

        if ext_name in ext_tree:
            raise ValueError(f"Duplicate Canary skills extension namespace: {ext_name}")

        ext_tree[ext_name] = ext_payload

    return tree


def normalize_extension_capabilities(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate and normalize one plugin capabilities payload."""
    document = extension_capabilities_schema.validate(payload)
    ext_name = document["extension"]
    capabilities = document["capabilities"]

    if not isinstance(capabilities, dict):
        raise TypeError(f"Capabilities payload for extension {ext_name!r} must be an object")

    return ext_name, capabilities


def normalize_extension_skills(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate and normalize one plugin skills payload."""
    document = extension_skills_schema.validate(payload)
    ext_name = document["extension"]
    skills = document["skills"]

    if not isinstance(skills, dict):
        raise TypeError(f"Skills payload for extension {ext_name!r} must be an object")

    return ext_name, skills


# -------------------------------------------------------------------------
# Listing helpers
# -------------------------------------------------------------------------


def list_capability_paths(data: Any, query: str) -> list[str]:
    """List immediate queryable child object paths below a capabilities query point."""
    selected = query_json(data, query)

    if not isinstance(selected, dict):
        return []

    prefix = display_query_prefix(query)

    rows: list[str] = []
    for key, value in sorted(selected.items(), key=lambda item: str(item[0])):
        if isinstance(value, dict):
            rows.append(join_query_path(prefix, str(key)))

    return rows


def list_skill_paths(data: Any, query: str) -> list[str]:
    """List terminal skill object paths below a skill query point."""
    selected = query_json(data, query)
    prefix = display_query_prefix(query)

    rows: list[str] = []
    for path, _skill in iter_skill_objects(selected, prefix=prefix):
        rows.append(path)

    return sorted(rows)


def list_json_object_paths(data: Any, query: str) -> list[str]:
    """List immediate child object paths for generic JSON job/session queries."""
    selected = query_json(data, query)

    if not isinstance(selected, dict):
        return []

    prefix = display_query_prefix(query)

    rows: list[str] = []
    for key, value in sorted(selected.items(), key=lambda item: str(item[0])):
        if isinstance(value, dict):
            rows.append(join_query_path(prefix, str(key)))

    return rows


def print_query_paths(paths: list[str]) -> None:
    for path in paths:
        print(path)


def display_query_prefix(query: str) -> str:
    query = query.strip()

    if not query or query == ".":
        return ""

    return query[1:] if query.startswith(".") else query


def join_query_path(prefix: str, key: str) -> str:
    if not prefix:
        return key

    if is_simple_query_key(key):
        return f"{prefix}.{key}"

    escaped = key.replace("\\", "\\\\").replace('"', '\\"')
    return f'{prefix}["{escaped}"]'


def is_simple_query_key(key: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key))


# -------------------------------------------------------------------------
# Skill helpers
# -------------------------------------------------------------------------


def is_skill_object(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and isinstance(data.get("name"), str)
        and isinstance(data.get("description"), str)
        and isinstance(data.get("body"), str)
    )


def iter_skill_objects(data: Any, *, prefix: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield ``(query_path, skill_object)`` pairs below ``data``."""
    if is_skill_object(data):
        yield prefix, data
        return

    if not isinstance(data, dict):
        return

    for key, value in data.items():
        child_prefix = join_query_path(prefix, str(key))
        yield from iter_skill_objects(value, prefix=child_prefix)


def write_skill_markdown(selector: str, data: Any, path: Path) -> None:
    """Write selected skill data as Markdown.

    If ``data`` is a single skill object, ``path`` is treated as a file unless it
    already exists as a directory.

    If ``data`` is a subtree containing multiple skill objects, ``path`` is
    treated as an output directory and namespace directories are preserved.
    """
    if is_skill_object(data):
        output = path

        if output.exists() and output.is_dir():
            output = output / f"{data['name']}.md"

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(skill_to_markdown(data), encoding="utf-8")
        return

    skills = list(iter_skill_objects(data, prefix=display_query_prefix(selector)))

    if not skills:
        raise ValueError("Selected skill query does not contain any skill objects")

    if path.exists() and not path.is_dir():
        raise ValueError(
            "Selected skill query resolved to a subtree, so --markdown PATH must be a directory"
        )

    path.mkdir(parents=True, exist_ok=True)

    for query_path, skill in skills:
        parts = [part for part in query_path.split(".") if part]
        if not parts:
            parts = [skill["name"]]

        output_dir = path.joinpath(*parts[:-1])
        output_dir.mkdir(parents=True, exist_ok=True)

        output = output_dir / f"{skill['name']}.md"
        output.write_text(skill_to_markdown(skill), encoding="utf-8")


def skill_to_markdown(skill: dict[str, Any]) -> str:
    """Convert a skill JSON object back to SKILL.md-style Markdown."""
    body = skill.get("body", "")

    if not isinstance(body, str):
        raise ValueError("Skill object must contain a string field: body")

    frontmatter = {key: value for key, value in skill.items() if key != "body"}

    name = frontmatter.get("name")
    description = frontmatter.get("description")

    if not isinstance(name, str) or not name:
        raise ValueError("Skill object must contain a non-empty string field: name")

    if not isinstance(description, str):
        raise ValueError("Skill object must contain a string field: description")

    frontmatter_text = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).rstrip()

    markdown = f"---\n{frontmatter_text}\n---\n\n{body}"

    if not markdown.endswith("\n"):
        markdown += "\n"

    return markdown


# -------------------------------------------------------------------------
# Query path evaluator
# -------------------------------------------------------------------------


def query_json(data: Any, query: str) -> Any:
    query = query.strip()

    if not query or query == ".":
        return data

    if not query.startswith("."):
        query = "." + query

    current = data

    for token in parse_query(query):
        if isinstance(token, str):
            if not isinstance(current, dict):
                raise TypeError(
                    f"Cannot access key {token!r} on {type(current).__name__}; "
                    f"current value is not an object"
                )
            try:
                current = current[token]
            except KeyError:
                raise KeyError(format_missing_key_message(token, current)) from None

        elif isinstance(token, int):
            if not isinstance(current, list):
                raise TypeError(
                    f"Cannot access index {token} on {type(current).__name__}; "
                    f"current value is not an array"
                )
            try:
                current = current[token]
            except IndexError:
                n = len(current)
                raise IndexError(f"No such index: {token}. Array length is {n}.") from None

        else:
            raise TypeError(f"Unsupported query token: {token!r}")

    return current


def format_missing_key_message(key: str, current: dict[str, Any]) -> str:
    keys = sorted(str(k) for k in current.keys())

    if not keys:
        return f"No such key: {key!r}. Current object has no keys."

    preview = ", ".join(keys[:24])
    if len(keys) > 24:
        preview += ", ..."

    return f"No such key: {key!r}. Available keys: {preview}"


def parse_query(query: str) -> list[str | int]:
    tokens: list[str | int] = []
    i = 0

    while i < len(query):
        ch = query[i]

        if ch == ".":
            i += 1
            start = i

            while i < len(query) and query[i] not in ".[":
                i += 1

            if i > start:
                tokens.append(query[start:i])

            continue

        if ch == "[":
            token, i = parse_bracket(query, i)
            tokens.append(token)
            continue

        raise ValueError(f"Invalid query syntax at column {i + 1}: {query!r}")

    return tokens


def parse_bracket(query: str, i: int) -> tuple[str | int, int]:
    assert query[i] == "["
    j = i + 1

    if j >= len(query):
        raise ValueError(f"Unclosed bracket in query: {query!r}")

    if query[j] in ("'", '"'):
        quote = query[j]
        j += 1
        chars: list[str] = []

        while j < len(query):
            ch = query[j]

            if ch == "\\":
                if j + 1 >= len(query):
                    raise ValueError(f"Invalid escape in query: {query!r}")
                chars.append(query[j + 1])
                j += 2
                continue

            if ch == quote:
                j += 1
                if j >= len(query) or query[j] != "]":
                    raise ValueError(f"Expected closing bracket in query: {query!r}")
                return "".join(chars), j + 1

            chars.append(ch)
            j += 1

        raise ValueError(f"Unclosed quoted key in query: {query!r}")

    match = re.match(r"-?\d+", query[j:])
    if match:
        value = int(match.group(0))
        j += len(match.group(0))
        if j >= len(query) or query[j] != "]":
            raise ValueError(f"Expected closing bracket in query: {query!r}")
        return value, j + 1

    raise ValueError(f"Invalid bracket expression in query: {query!r}")


def print_capability_query_help() -> None:
    data = build_capabilities_tree()
    top_level = list_capability_paths(data, ".")

    print(
        """\
Canary capability queries inspect the aggregated core + extension capability tree.

Usage:
  canary query -c QUERY
  canary query -c QUERY --list

Examples:
  canary query -c .
  canary query -c overview
  canary query -c hooks.post
  canary query -c ext --list
  canary query -c ext.pyt.overview

Top-level capability keys:"""
    )

    for key in top_level:
        print(f"  {key}")

    print(
        """
Tips:
  Use '.' for the root capability tree.
  Use '--list' to list queryable keys below a point.
  Extension capabilities live under 'ext.<extension-name>'.
"""
    )


def print_skill_query_help() -> None:
    data = build_skills_tree()
    top_level = list_skill_paths(data, ".")

    print(
        """\
Canary skill queries inspect the aggregated core + extension skill tree.

Usage:
  canary query -k QUERY
  canary query -k QUERY --list
  canary query -k QUERY --markdown PATH

Examples:
  canary query -k .
  canary query -k canary-orientation
  canary query -k . --list
  canary query -k ext.pyt --list
  canary query -k ext.pyt.canary-pyt-authoring
  canary query -k canary-orientation --markdown canary-orientation.md

Available skills:"""
    )

    for key in top_level:
        print(f"  {key}")

    print(
        """
Tips:
  Use '.' for the root skill tree.
  Use '--list' to list skill keys below a point.
  Extension skills live under 'ext.<extension-name>'.
  Use '--markdown PATH' to export a skill or skill subtree.
"""
    )


# -------------------------------------------------------------------------
# Errors
# -------------------------------------------------------------------------


class CapabilityDatasetNotFoundError(FileNotFoundError):
    def __init__(self, path: Any) -> None:
        self.path = path
        super().__init__(f"Canary capability database not found: {path}")


class SkillDatasetNotFoundError(FileNotFoundError):
    def __init__(self, path: Any) -> None:
        self.path = path
        super().__init__(f"Canary skills database not found: {path}")


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Query())
