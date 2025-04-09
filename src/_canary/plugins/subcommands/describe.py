# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import os
from typing import TYPE_CHECKING

from ...generator import AbstractTestGenerator
from ...test.case import TestCase
from ..hookspec import hookimpl
from ..types import CanarySubcommand
from .common import add_filter_arguments
from .common import add_resource_arguments
from .common import load_session

if TYPE_CHECKING:
    from ...config.argparsing import Parser


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return Describe()


class Describe(CanarySubcommand):
    name = "describe"
    description = "Print information about a test file or test case"

    def setup_parser(self, parser: "Parser") -> None:
        add_filter_arguments(parser)
        add_resource_arguments(parser)
        parser.add_argument("testspec", help="Test file or test case spec")

    def execute(self, args: argparse.Namespace) -> int:
        import _canary.finder as finder

        if os.path.isdir(args.testspec):
            path = args.testspec
            return describe_folder(
                path,
                keyword_exprs=args.keyword_exprs,
                on_options=args.on_options,
                parameter_expr=args.parameter_expr,
            )
        if finder.is_test_file(args.testspec):
            file = finder.find(args.testspec)
            return describe_generator(file, on_options=args.on_options)
        # could be a test case in the test session?
        session = load_session()
        for case in session.cases:
            if case.matches(args.testspec):
                describe_testcase(case)
                return 0
        print(f"{args.testspec}: could not find matching generator or test case")
        return 1


def describe_folder(
    path: str,
    keyword_exprs: list[str] | None = None,
    on_options: list[str] | None = None,
    parameter_expr: str | None = None,
) -> int:
    import _canary.finder as finder

    f = finder.Finder()
    f.add(path)
    f.prepare()
    files = f.discover()
    for file in sorted(files, key=lambda f: f.file):
        describe_generator(file, on_options=on_options)
        print()
    return 0


def describe_generator(
    file: AbstractTestGenerator,
    on_options: list[str] | None = None,
) -> int:
    description = file.describe(on_options=on_options)
    print(description.rstrip())
    return 0


def describe_testcase(case: TestCase, indent: str = "") -> int:
    if case.work_tree is None:
        case.work_tree = "."
    d = dict(vars(case))
    d["status"] = (case.status.value, case.status.details)
    d["logfile"] = case.logfile()
    print(f"{indent}{case}")
    for key in sorted(d):
        if not key.startswith("_"):
            print(f"{indent}  {key}: {d[key]}")
    return 0
