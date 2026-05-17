# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from ... import when
from ...hookspec import hookimpl
from ...select import Selector
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testcase import Job

logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Rebaseline())


class Rebaseline(CanarySubcommand):
    name = "rebaseline"
    description = "Rebaseline tests"

    @staticmethod
    def inview_dir(arg: str) -> str:
        workspace = Workspace.load()
        if workspace.relative_to_view(arg):
            return arg
        raise ValueError(f"{arg}: is not in a view")

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "start", nargs="?", type=self.inview_dir, help="Find tests in this view"
        )
        Selector.setup_parser(parser, tagged="none")

    def execute(self, args: "argparse.Namespace") -> int:
        if not args.keyword_exprs and not args.start and not args.parameter_expr:
            raise ValueError("At least one filtering criteria required")
        workspace = Workspace.load()
        jobs: list[Job]
        if args.start:
            specs = workspace.select_from_view(path=Path(args.start))
            jobs = workspace.load_jobs(ids=[spec.id for spec in specs])
        else:
            jobs = workspace.load_jobs(args.job_specs)
        if args.keyword_exprs:
            jobs = filter_cases_by_keyword(jobs, args.keyword_exprs)
        for job in jobs:
            job.do_baseline()
        return 0


def filter_cases_by_keyword(jobs: list["Job"], keyword_exprs: list[str]) -> list["Job"]:
    masks: dict[str, bool] = {}
    for job in jobs:
        kwds = set(job.spec.keywords)
        kwds.update(job.spec.implicit_keywords)  # ty: ignore[invalid-argument-type]
        kwd_all = (":all:" in keyword_exprs) or ("__all__" in keyword_exprs)
        if not kwd_all:
            for keyword_expr in keyword_exprs:
                match = when.when({"keywords": keyword_expr}, keywords=list(kwds))
                if not match:
                    masks[job.id] = True
                    break
    return [job for job in jobs if not masks.get(job.id)]
