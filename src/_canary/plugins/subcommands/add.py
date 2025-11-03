# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from typing import TYPE_CHECKING

from ...repo import Repo
from ...util import logging
from ..hookspec import hookimpl
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser


logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Add())


class pathspec(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        spec: dict[str, list[str]] = {}
        for value in values:
            if os.path.isfile(value):
                d, f = os.path.split(os.path.abspath(value))
                spec.setdefault(d, []).append(f)
            elif os.path.isdir(value):
                spec.setdefault(value, [])
            elif ":" in value:
                d, _, f = value.partition(":")
                if not os.path.exists(os.path.join(d, f)):
                    parser.error(f"{f} not found in {d}")
                else:
                    spec.setdefault(d, []).append(f)
            elif value.startswith(("git@", "repo@")):
                vcs, _, root = value.partition("@")
                if not os.path.isdir(root):
                    parser.error(f"{vcs}@{root}: directory does not exist")
            else:
                parser.error(f"{value}: file does not exit")
        setattr(namespace, self.dest, spec)


class Add(CanarySubcommand):
    name = "add"
    description = "Add test generators to Canary session"

    def setup_parser(self, parser: "Parser"):
        parser.add_argument(
            "pathspec",
            action=pathspec,
            nargs="+",
            help="Add test generators found in pathspec to Canary session",
        )

    def execute(self, args: "argparse.Namespace") -> int:
        repo = Repo.load()
        generators = repo.collect_testcase_generators(args.pathspec, pedantic=True)
        logger.info(f"Added {len(generators)} test case generators to {repo.root.parent}")
        return 0
