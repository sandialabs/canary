# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import json
import re
import sys
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import yaml

from ..hookspec import hookimpl
from ..workspace import Workspace
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


class Query(CanarySubcommand):
    name = "query"
    description = "Query Canary job/session lock files or static capability data"

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
            metavar="CAPABILITY",
            help=(
                "Query Canary's static capability database. "
                "'-c all' or '-c capabilities' prints the whole database. "
                "Other values are shortcuts into the database, for example "
                "'-c overview' is equivalent to '-c capabilities .overview'."
            ),
        )
        group.add_argument(
            "-k",
            "--skill",
            dest="skill",
            metavar="SKILL",
            help=(
                "Query Canary's static skills database. "
                "'--skill all' prints all skills. '--skill list' lists skill names "
                "Otherwise, SKILL is interpreted as a skill name."
            ),
        )
        parser.add_argument("--terse", action="store_true", help="Print compact single-line JSON")
        parser.add_argument(
            "--markdown",
            metavar="PATH",
            help=(
                "Write selected skill as Markdown. "
                "For a single skill, PATH is a Markdown file. "
                "For '--skill all', PATH must be a directory."
            ),
        )
        parser.add_argument(
            "query",
            nargs="?",
            default=".",
            help="Query expression. If omitted, emit the whole selected JSON object.",
        )

    def execute(self, args: argparse.Namespace) -> int:
        if args.capability:
            if args.markdown:
                raise ValueError("--markdown is only valid with --skill")
            data = query_capabilities(args.capability, args.query)

        elif args.skill:
            data = query_skills(args.skill, args.query)
            if args.markdown:
                write_skill_markdown(args.skill, data, Path(args.markdown))
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


def load_capability_dataset() -> Any:
    """
    Load Canary's static capability database.

    Canary currently ships exactly one static capability database:
    ``canary/data/capabilities.json``.

    The command-line ``-c`` selector is intentionally not a dataset selector.
    It is a capability selector:

    - ``-c all`` prints the whole capabilities database.
    - ``-c capabilities`` also prints the whole capabilities database.
    - ``-c overview`` is a shortcut for ``-c capabilities .overview``.
    - ``-c hooks.post`` is a shortcut for ``-c capabilities .hooks.post``.
    """
    path = resources.files("canary").joinpath("data").joinpath("capabilities.json")
    if not path.is_file():
        raise CapabilityDatasetNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))["capabilities"]


def query_capabilities(selector: str, query: str = ".") -> Any:
    """
    Query Canary's static capability database.

    Args:
        selector:
            Capability selector from ``-c``. ``all`` and ``capabilities`` select
            the whole database. Any other selector is interpreted as a shortcut
            path into the database.
        query:
            Optional additional query path. For shortcut selectors, the query
            is appended below the selected shortcut path.

    Examples:
        ``query_capabilities("all")`` returns the full database.

        ``query_capabilities("capabilities", ".overview")`` returns
        ``.overview``.

        ``query_capabilities("overview")`` returns ``.overview``.

        ``query_capabilities("hooks.post")`` returns ``.hooks.post``.

        ``query_capabilities("hooks", ".post")`` returns ``.hooks.post``.
    """
    data = load_capability_dataset()
    selector = selector.strip()
    query = query.strip()

    if not selector:
        raise ValueError("Capability selector must be non-empty")

    if selector in ("all", "capabilities"):
        return query_json(data, query)

    shortcut = selector if selector.startswith(".") else f".{selector}"

    if query and query != ".":
        suffix = query[1:] if query.startswith(".") else query
        if suffix:
            shortcut = f"{shortcut}.{suffix}"

    return query_json(data, shortcut)


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


def load_skill_dataset() -> Any:
    """
    Load Canary's static skills database.

    Canary ships one static skills database:

        canary/data/skills.json

    Expected shape:

        {
          "skill-name": {
            "name": "skill-name",
            "description": "...",
            "body": "..."
          }
        }
    """
    path = resources.files("canary").joinpath("data").joinpath("skills.json")
    if not path.is_file():
        raise SkillDatasetNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))["skills"]


def query_skills(selector: str, query: str = ".") -> Any:
    """
    Query Canary's static skills database.

    Args:
        selector:
            Skill selector from ``--skill``. ``all`` selects the whole database.
            Any other selector is interpreted as a skill name.
        query:
            Optional query path below the selected skill.

    Examples:
        ``query_skills("all")`` returns the full skills database.

        ``query_skills("canary-workflows-results")`` returns that skill object.

        ``query_skills("canary-workflows-results", ".description")`` returns
        the selected skill's description.

        ``query_skills("canary-workflows-results", "body")`` returns the
        selected skill's Markdown body.
    """
    data = load_skill_dataset()
    selector = selector.strip()
    query = query.strip()

    if not selector:
        raise ValueError("Skill selector must be non-empty")

    if selector == "all":
        return query_json(data, query)

    if selector == "list":
        return list(data.keys())

    try:
        skill = data[selector]
    except KeyError:
        raise KeyError(format_missing_key_message(selector, data)) from None

    return query_json(skill, query)


def write_skill_markdown(selector: str, data: Any, path: Path) -> None:
    """
    Write selected skill data as Markdown.

    If selector is "all", data should be the entire skills object and path must
    be a directory. Each skill is written as NAME.md.

    If selector is a single skill, data should be a skill object and path is the
    output Markdown file.
    """
    if selector == "all":
        if not isinstance(data, dict):
            raise TypeError("--skill all must resolve to an object when writing Markdown")

        path.mkdir(parents=True, exist_ok=True)

        for name, skill in data.items():
            if not isinstance(skill, dict):
                raise TypeError(f"Skill {name!r} is not an object")
            markdown = skill_to_markdown(skill)
            output = path / f"{name}.md"
            output.write_text(markdown, encoding="utf-8")

        return

    if not isinstance(data, dict):
        raise TypeError(
            "--markdown requires the selected skill object. "
            "Do not combine --markdown with a field query such as '.body'."
        )

    markdown = skill_to_markdown(data)

    if path.exists() and path.is_dir():
        name = data.get("name", selector)
        path = path / f"{name}.md"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def skill_to_markdown(skill: dict[str, Any]) -> str:
    """
    Convert a skill JSON object back to SKILL.md-style Markdown.
    """
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
