# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import io
import sys
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator

import rich

from . import config
from .hookspec import hookimpl
from .util import glyphs
from .util import logging
from .util.returncode import compute_returncode
from .util.time import hhmmss

if TYPE_CHECKING:
    from .config.argparsing import Parser
    from .status import Outcome
    from .testcase import Job
    from .workspace import Workspace


logger = logging.get_logger(__name__)


def canary_runtests(runner: "Runner") -> None:
    pm = config.pluginmanager.hook
    try:
        logger.info(f"[bold]Starting[/] session {runner.session}")
        pm.canary_runtests_start(runner=runner)
        with runner.timeit():
            pm.canary_runtests(runner=runner)
    except TimeoutError:
        logger.error(f"Session timed out after {(time.time() - runner.start):.2f} s.")
        raise
    except Exception:
        logger.exception("Unhandled exception in canary_runtest")
        raise
    finally:
        logger.info(
            f"[bold]Finished[/] session in {(runner.finish - runner.start):.2f} s. "
            f"with returncode {runner.returncode}"
        )
        pm.canary_runtests_report(runner=runner)
    return


@dataclasses.dataclass
class Runner:
    jobs: list["Job"]
    session: str
    workspace: "Workspace"
    _returncode: int = -20
    start: float = dataclasses.field(default=-1.0, init=False)
    finish: float = dataclasses.field(default=-1.0, init=False)

    @property
    def returncode(self) -> int:
        if self._returncode == -20:
            self._returncode = compute_returncode(self.jobs)
        return self._returncode

    @contextmanager
    def timeit(self) -> Generator[None, None, None]:
        try:
            self.start = time.time()
            yield
        finally:
            self.finish = time.time()


@hookimpl(wrapper=True)
def canary_runteststart(case: "Job") -> Generator[None, None, bool]:
    case.workspace.create(exist_ok=True)
    case.setup()
    yield
    case.save()
    return True


@hookimpl(wrapper=True)
def canary_runtest(case: "Job") -> Generator[None, None, bool]:
    case.run()
    yield
    case.save()
    return True


@hookimpl(wrapper=True)
def canary_runtest_finish(case: "Job") -> Generator[None, None, bool]:
    case.finish()
    yield
    case.save()
    return True


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    def add_group_argument(p: "Parser", *args: Any, **kwargs: Any):
        p.add_argument(*args, group="console reporting", command="run", **kwargs)

    add_group_argument(
        parser,
        "--no-summary",
        action="store_true",
        help="Disable summary [default: %(default)s]",
    )
    add_group_argument(
        parser,
        "--durations",
        type=int,
        metavar="N",
        help="Show N slowest test durations (N<0 for all)",
    )


@hookimpl(specname="canary_runtests_report", tryfirst=True)
def print_short_test_status_summary(runner: Runner) -> None:
    """Return a summary of the completed jobs.  if ``include_pass is True``, include
    passed tests in the summary

    """
    from .status import Category

    if not config.get("debug") or config.getoption("no_summary"):
        return
    include_pass = False
    truncate = 10
    file = io.StringIO()
    if not runner.jobs:
        file.write("Nothing to report\n")
    else:
        totals: dict[tuple[Category, "Outcome"], list["Job"]] = {}
        for job in runner.jobs:
            key = (job.status.category, job.status.outcome)
            totals.setdefault(key, []).append(job)
        for key in totals:
            if not include_pass and key[0] == Category.PASS:
                continue
            n: int = 0
            for job in sorted(totals[key], key=lambda t: t.name):
                file.write(job.statline(style="rich") + "\n")
                n += 1
                if truncate > 0 and truncate == n:
                    file.write(f"... truncating summary to the first {truncate} entries.\n")
                    file.write("See [bold]canary status[/bold] for the full summary\n")
                    break
    string = file.getvalue()
    if string.strip():
        string = "\n[bold]Short test summary info[/bold]\n" + string
    rich.print(string, file=sys.stderr)


@hookimpl(specname="canary_runtests_report")
def print_runtests_durations(runner: Runner) -> None:
    if N := config.getoption("durations"):
        return print_durations(runner.jobs, N)


@hookimpl(specname="canary_runtests_report", trylast=True)
def runtests_footer(runner: Runner) -> None:
    """Return a short, high-level, summary of test results"""
    if config.get("debug"):
        print_footer(runner, "Session done")


def print_footer(runner: "Runner", title: str) -> None:
    """Return a short, high-level, summary of test results"""
    from . import status

    def sortkey(x: tuple[status.Category, status.Outcome]) -> tuple[int, status.Outcome]:
        n = 0 if x[0] == status.Category.PASS else 2 if x[0] == status.Category.FAIL else 1
        return (n, x[1])

    duration = runner.finish - runner.start
    totals: dict[tuple[status.Category, status.Outcome], list["Job"]] = {}
    for job in runner.jobs:
        key = (job.status.category, job.status.outcome)
        totals.setdefault(key, []).append(job)
    N = len(runner.jobs)
    summary = [f"[bold blue]{N} total[/bold blue]:"]
    for category, outcome in sorted(totals, key=sortkey):
        n = len(totals[(category, outcome)])
        if n:
            color = category.rich_color()
            t = category if outcome == status.Outcome.SUCCESS else outcome
            summary.append(f"[{color}]{n} {t.name.lower()}[/{color}]")
    kwds = {
        "s": summary[0] + " " + ", ".join(summary[1:]),
        "t": hhmmss(None if duration < 0 else duration),
        "title": title,
    }
    logger.log(
        logging.EMIT,
        "[bold]%(title)s[/bold] -- %(s)s in [bold]%(t)s[/bold]" % kwds,
        extra={"prefix": f"{glyphs.sparkles}{glyphs.sparkles} "},
    )


def print_durations(jobs: list["Job"], N: int) -> None:
    jobs.sort(key=lambda x: x.timekeeper.duration())
    ix = list(range(len(jobs)))
    if N > 0:
        ix = ix[-N:]
    kwds = {"t": glyphs.turtle, "N": N}
    fp = io.StringIO()
    fp.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
    for i in ix:
        duration = jobs[i].timekeeper.duration()
        if duration < 0:
            continue
        name = jobs[i].display_name(style="rich")
        id = jobs[i].id[:7]
        fp.write("  %6.2f   %s %s\n" % (duration, id, name))
    rich.print(fp.getvalue().strip(), file=sys.stderr)
