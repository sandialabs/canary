# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from .. import config
from ..config.schemas import capabilities_provider_schema
from ..config.schemas import skills_provider_schema
from ..hookspec import hookimpl
from ..util.query_data import display_query_prefix
from ..util.query_data import iter_skill_objects
from ..util.query_data import list_json_object_paths
from ..util.query_data import print_json
from ..util.query_data import print_query_paths
from ..util.query_data import query_json
from ..util.query_data import write_skill_markdown
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


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
                "Capability query path. Examples: '.', 'core.overview', "
                "'core.hooks.post', 'pyt.overview'. If omitted, print query guidance."
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
                "Skill query path. Examples: '.', 'core.canary-orientation', "
                "'pyt.canary-pyt-authoring'. If omitted, print query guidance."
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
  canary learn capabilities .
  canary learn capabilities core.overview
  canary learn capabilities core.hooks.post
  canary learn capabilities pyt.overview
  canary learn capabilities . --list
  canary learn capabilities pyt --list

  canary learn skills .
  canary learn skills core.canary-orientation
  canary learn skills . --list
  canary learn skills pyt --list
  canary learn skills pyt.canary-pyt-authoring
"""
    )


def print_capability_query_help() -> None:
    data = build_capabilities_tree()
    top_level = list_capability_paths(data, ".")

    print(
        """\
Canary capability queries inspect the aggregated capability tree.

Usage:
  canary learn capabilities QUERY
  canary learn capabilities QUERY --list

Examples:
  canary learn capabilities .
  canary learn capabilities core.overview
  canary learn capabilities core.hooks.post
  canary learn capabilities pyt.overview
  canary learn capabilities . --list
  canary learn capabilities pyt --list

Top-level capability namespaces:"""
    )

    for key in top_level:
        print(f"  {key}")

    print(
        """
Tips:
  Use '.' for the root capability tree.
  Use '--list' to list queryable keys below a point.
  Each provider contributes data under its namespace, such as 'core', 'pyt', or 'hpc'.
"""
    )


def print_skill_query_help() -> None:
    data = build_skills_tree()
    skills = list_skill_paths(data, ".")

    print(
        """\
Canary skill queries inspect the aggregated skill tree.

Usage:
  canary learn skills QUERY
  canary learn skills QUERY --list
  canary learn skills QUERY --markdown PATH

Examples:
  canary learn skills .
  canary learn skills core.canary-orientation
  canary learn skills . --list
  canary learn skills pyt --list
  canary learn skills pyt.canary-pyt-authoring
  canary learn skills core.canary-orientation --markdown canary-orientation.md

Available skills:"""
    )

    for key in skills:
        print(f"  {key}")

    print(
        """
Tips:
  Use '.' for the root skill tree.
  Use '--list' to list skill keys below a point.
  Each provider contributes skills under its namespace, such as 'core', 'pyt', or 'hpc'.
  Use '--markdown PATH' to export a skill or skill subtree.
"""
    )


# -------------------------------------------------------------------------
# Capability / skill provider aggregation
# -------------------------------------------------------------------------


def build_capabilities_tree() -> dict[str, Any]:
    """Build the runtime aggregate capabilities tree.

    Every provider contributes a document with a namespace. The aggregate shape is:

        {
          "core": {...},
          "pyt": {...},
          "vvtest": {...}
        }

    Providers may be backed by static JSON, dynamic Python dictionaries,
    introspection, or future external systems.
    """
    tree: dict[str, Any] = {}
    payloads = config.pluginmanager.hook.canary_capabilities()

    for payload in payloads:
        if payload is None:
            continue

        namespace, capabilities = normalize_capabilities_provider(payload)

        if namespace in tree:
            raise ValueError(f"Duplicate Canary capabilities namespace: {namespace}")

        tree[namespace] = capabilities

    return tree


def build_skills_tree() -> dict[str, Any]:
    """Build the runtime aggregate skills tree.

    Every provider contributes a document with a namespace. The aggregate shape is:

        {
          "core": {...},
          "pyt": {...},
          "vvtest": {...}
        }

    Providers may be backed by static JSON, dynamic Python dictionaries,
    introspection, or future external systems.
    """
    tree: dict[str, Any] = {}
    payloads = config.pluginmanager.hook.canary_skills()

    for payload in payloads:
        if payload is None:
            continue

        namespace, skills = normalize_skills_provider(payload)

        if namespace in tree:
            raise ValueError(f"Duplicate Canary skills namespace: {namespace}")

        tree[namespace] = skills

    return tree


def normalize_capabilities_provider(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate and normalize one capabilities provider payload."""
    document = capabilities_provider_schema.validate(payload)
    namespace = document["namespace"]
    capabilities = document["capabilities"]

    if not isinstance(capabilities, dict):
        raise TypeError(f"Capabilities payload for namespace {namespace!r} must be an object")

    return namespace, capabilities


def normalize_skills_provider(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate and normalize one skills provider payload."""
    document = skills_provider_schema.validate(payload)
    namespace = document["namespace"]
    skills = document["skills"]

    if not isinstance(skills, dict):
        raise TypeError(f"Skills payload for namespace {namespace!r} must be an object")

    return namespace, skills


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


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Learn())
