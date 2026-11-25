# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from typing import TYPE_CHECKING

from ..app import learn
from ..app.learn import build_capabilities_tree
from ..app.learn import build_skills_tree
from ..app.learn import list_capability_paths
from ..app.learn import list_skill_paths
from ..plugins.hookspec import hookimpl
from ..util.query_data import print_json
from ..util.query_data import print_query_paths
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
        return execute_capabilities_query(args.query, terse=args.terse, list_keys=args.list_keys)

    def run_skills(self, args: argparse.Namespace) -> int:
        return execute_skills_query(args.query, terse=args.terse, list_keys=args.list_keys)


def execute_capabilities_query(query: str, *, terse: bool = False, list_keys: bool = False) -> int:
    if query == CAPABILITY_HELP_QUERY:
        if list_keys:
            query = "."
        else:
            print_capability_query_help()
            return 0

    result = learn.capabilities(query, list_keys=list_keys)
    if list_keys:
        print_query_paths(result)
    else:
        print_json(result, terse=terse)
    return 0


def execute_skills_query(query: str, *, terse: bool = False, list_keys: bool = False) -> int:
    if query == SKILL_HELP_QUERY:
        if list_keys:
            query = "."
        else:
            print_skill_query_help()
            return 0

    result = learn.skills(query, list_keys=list_keys)
    if list_keys:
        print_query_paths(result)
    else:
        print_json(result, terse=terse)
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

Examples:
  canary learn skills .
  canary learn skills core.canary-orientation
  canary learn skills . --list
  canary learn skills pyt --list
  canary learn skills pyt.canary-pyt-authoring

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
"""
    )


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Learn())
