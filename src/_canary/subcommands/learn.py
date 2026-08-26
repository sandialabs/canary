# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from .. import config
from ..config.schemas import core_capabilities_schema
from ..config.schemas import core_skills_schema
from ..config.schemas import extension_capabilities_schema
from ..config.schemas import extension_skills_schema
from ..hookspec import hookimpl
from ..util.query_data import display_query_prefix
from ..util.query_data import iter_skill_objects
from ..util.query_data import list_json_object_paths
from ..util.query_data import print_json
from ..util.query_data import print_query_paths
from ..util.query_data import query_json
from ..util.query_data import require_query_data
from ..util.query_data import write_skill_markdown
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


CAPABILITIES_RESOURCE = "capabilities.json"
SKILLS_RESOURCE = "skills.json"

CAPABILITY_HELP_QUERY = "__canary_capability_help__"
SKILL_HELP_QUERY = "__canary_skill_help__"


class Learn(CanarySubcommand):
    name = "learn"
    description = "Query installed Canary capabilities and skills"

    def setup_parser(self, parser: "Parser") -> None:
        subparsers = parser.add_subparsers(dest="learn_command", metavar="topic")

        capability_parser = subparsers.add_parser(
            "capabilities",
            aliases=("capability", "caps", "cap"),
            help="Query the aggregated Canary capability tree",
        )
        capability_parser.add_argument("--terse", action="store_true", help="Print compact JSON")
        capability_parser.add_argument(
            "--list",
            action="store_true",
            dest="list_keys",
            help="List queryable capability keys below the selected query point",
        )
        capability_parser.add_argument(
            "query",
            nargs="?",
            default=CAPABILITY_HELP_QUERY,
            help=(
                "Capability query path. Examples: '.', 'overview', 'hooks.post', "
                "'ext.pyt.overview'. If omitted, print query guidance."
            ),
        )
        capability_parser.set_defaults(_learn_handler=self.run_capabilities)

        skill_parser = subparsers.add_parser(
            "skills", aliases=("skill",), help="Query the aggregated Canary skill tree"
        )
        skill_parser.add_argument("--terse", action="store_true", help="Print compact JSON")
        skill_parser.add_argument(
            "--list",
            action="store_true",
            dest="list_keys",
            help="List skill keys below the selected query point",
        )
        skill_parser.add_argument(
            "--markdown",
            metavar="PATH",
            help=(
                "Write selected skill or skill subtree as Markdown. "
                "For a single skill, PATH is a Markdown file or an existing directory. "
                "For a skill subtree, PATH is an output directory."
            ),
        )
        skill_parser.add_argument(
            "query",
            nargs="?",
            default=SKILL_HELP_QUERY,
            help=(
                "Skill query path. Examples: '.', 'canary-orientation', "
                "'ext.pyt.canary-pyt-authoring'. If omitted, print query guidance."
            ),
        )
        skill_parser.set_defaults(_learn_handler=self.run_skills)

    def execute(self, args: argparse.Namespace) -> int:
        handler = getattr(args, "_learn_handler", None)

        if handler is None:
            print_learn_help()
            return 0

        return handler(args)

    def run_capabilities(self, args: argparse.Namespace) -> int:
        query = args.query

        if query == CAPABILITY_HELP_QUERY:
            if args.list_keys:
                query = "."
            else:
                print_capability_query_help()
                return 0

        data = build_capabilities_tree()

        if args.list_keys:
            print_query_paths(list_capability_paths(data, query))
            return 0

        result = query_json(data, query)
        print_json(result, terse=args.terse)
        return 0

    def run_skills(self, args: argparse.Namespace) -> int:
        query = args.query

        if query == SKILL_HELP_QUERY:
            if args.list_keys:
                query = "."
            else:
                print_skill_query_help()
                return 0

        data = build_skills_tree()

        if args.list_keys:
            print_query_paths(list_skill_paths(data, query))
            return 0

        result = query_json(data, query)

        if args.markdown:
            write_skill_markdown(query, result, Path(args.markdown))
            return 0

        print_json(result, terse=args.terse)
        return 0


# -------------------------------------------------------------------------
# User-facing help
# -------------------------------------------------------------------------


def print_learn_help() -> None:
    print(
        """\
Canary learn queries installed Canary knowledge.

Usage:
  canary learn capabilities QUERY
  canary learn capabilities QUERY --list
  canary learn skills QUERY
  canary learn skills QUERY --list
  canary learn skills QUERY --markdown PATH

Examples:
  canary learn capabilities overview
  canary learn capabilities hooks.post
  canary learn capabilities ext --list
  canary learn capabilities ext.pyt.overview

  canary learn skills --list
  canary learn skills canary-orientation
  canary learn skills ext.pyt --list
  canary learn skills ext.pyt.canary-pyt-authoring
"""
    )


def print_capability_query_help() -> None:
    data = build_capabilities_tree()
    top_level = list_capability_paths(data, ".")

    print(
        """\
Canary capability queries inspect the aggregated core + extension capability tree.

Usage:
  canary learn capabilities QUERY
  canary learn capabilities QUERY --list

Examples:
  canary learn capabilities .
  canary learn capabilities overview
  canary learn capabilities hooks.post
  canary learn capabilities ext --list
  canary learn capabilities ext.pyt.overview

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
    skills = list_skill_paths(data, ".")

    print(
        """\
Canary skill queries inspect the aggregated core + extension skill tree.

Usage:
  canary learn skills QUERY
  canary learn skills QUERY --list
  canary learn skills QUERY --markdown PATH

Examples:
  canary learn skills .
  canary learn skills canary-orientation
  canary learn skills . --list
  canary learn skills ext.pyt --list
  canary learn skills ext.pyt.canary-pyt-authoring
  canary learn skills canary-orientation --markdown canary-orientation.md

Available skills:"""
    )

    for key in skills:
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
    return list_json_object_paths(data, query)


def list_skill_paths(data: Any, query: str) -> list[str]:
    """List terminal skill object paths below a skill query point."""
    selected = query_json(data, query)
    prefix = display_query_prefix(query)

    rows: list[str] = []
    for path, _skill in iter_skill_objects(selected, prefix=prefix):
        rows.append(path)

    return sorted(rows)


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
    parser.add_command(Learn())
