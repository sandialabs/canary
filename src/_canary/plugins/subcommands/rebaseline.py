# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from ... import when
from ...collect import Collector
from ...hookspec import hookimpl
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand
from .common import add_filter_arguments

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testcase import TestCase

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Rebaseline())


class Rebaseline(CanarySubcommand):
    name = "rebaseline"
    aliases = ["baseline"]
    description = "Rebaseline tests"

    def setup_parser(self, parser: "Parser") -> None:
        add_filter_arguments(parser)
        Collector.setup_parser(parser)

    def execute(self, args: "argparse.Namespace") -> int:
        if not args.keyword_exprs and not args.start and not args.parameter_expr:
            raise ValueError("At least one filtering criteria required")
        workspace = Workspace.load()
        cases: list[TestCase]
        if args.start:
            cases = workspace.select_from_path(path=Path(args.start))
        else:
            cases = workspace.load_testcases(args.case_specs)
        if args.keyword_exprs:
            cases = filter_cases_by_keyword(cases, args.keyword_exprs)
        for case in cases:
            case.do_baseline()
        return 0


def filter_cases_by_keyword(cases: list["TestCase"], keyword_exprs: list[str]) -> list["TestCase"]:
    masks: dict[str, bool] = {}
    for case in cases:
        kwds = set(case.spec.keywords)
        kwds.update(case.spec.implicit_keywords)  # ty: ignore[invalid-argument-type]
        kwd_all = (":all:" in keyword_exprs) or ("__all__" in keyword_exprs)
        if not kwd_all:
            for keyword_expr in keyword_exprs:
                match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                if not match:
                    masks[case.id] = True
                    break
    return [case for case in cases if not masks.get(case.id)]
