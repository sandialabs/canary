# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Iterable

from ...hookspec import hookimpl
from ...rules import KeywordRule
from ...util import json_helper as json
from ...util import logging
from ...workspace import Workspace
from ..types import CanarySubcommand

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...job import Job


logger = logging.get_logger(__name__)


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Rebaseline())


class Rebaseline(CanarySubcommand):
    name = "rebaseline"
    description = "Update baseline files from existing test results"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "-k",
            dest="keyword_exprs",
            metavar="KEYWORD_EXPR",
            action="append",
            help="Restrict rebaseline to jobs matching keyword expression",
        )
        parser.add_argument(
            "target",
            nargs="?",
            default=".",
            metavar="DIR_OR_JOBID",
            help=(
                "Directory containing test results or a job id/name. "
                "If a directory is given, testcase.lock files are found recursively. "
                "[default: current directory]"
            ),
        )

    def execute(self, args: argparse.Namespace) -> int:
        workspace = Workspace.load()

        jobs = list(resolve_rebaseline_jobs(workspace, args.target))
        jobs = filter_jobs_by_keywords(jobs, args.keyword_exprs)

        if not jobs:
            logger.warning("No jobs selected for rebaseline")
            return 0

        for job in jobs:
            logger.info(f"[bold]Rebaselining[/] {job.display_name(style='rich', resolve=True)}")
            job.do_baseline()

        logger.info(f"[bold]Rebaselined[/] {len(jobs)} job(s)")
        return 0


def resolve_rebaseline_jobs(workspace: Workspace, target: str) -> list["Job"]:
    path = Path(target)

    if path.exists():
        return jobs_from_path(path)

    return [workspace.find(job=target)]


def jobs_from_path(path: Path) -> list["Job"]:
    lockfiles = list(iter_lockfiles(path))
    jobs: list["Job"] = []
    seen: set[str] = set()

    for lockfile in lockfiles:
        job = load_job_from_lockfile(lockfile)
        if job.id in seen:
            continue
        seen.add(job.id)
        jobs.append(job)

    return jobs


def iter_lockfiles(path: Path):
    import os

    if path.is_file():
        if path.name != "testcase.lock":
            raise ValueError(f"{path}: expected testcase.lock")
        yield path
        return

    if not path.is_dir():
        raise ValueError(f"{path}: no such file or directory")

    for root, dirs, files in os.walk(path, followlinks=True):
        if "testcase.lock" in files:
            yield Path(root) / "testcase.lock"


def load_job_from_lockfile(path: Path) -> "Job":
    if not path.exists():
        raise FileNotFoundError(path)
    job = json.loads(path.read_text())
    return job


def filter_jobs_by_keywords(
    jobs: list["Job"], keyword_exprs: list[str] | None
) -> list["Job"]:
    if not keyword_exprs:
        return jobs

    rule = KeywordRule(keyword_exprs)
    selected: list["Job"] = []

    for job in jobs:
        outcome = rule(job.spec)
        if outcome:
            selected.append(job)

    return selected
