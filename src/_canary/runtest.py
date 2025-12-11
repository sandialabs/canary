# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import dataclasses
import io
import random
import time
from contextlib import contextmanager
from multiprocessing import Queue
from typing import TYPE_CHECKING
from typing import Any
from typing import Generator

import rich

from . import config
from .hookspec import hookimpl
from .status import Status
from .util import glyphs
from .util import logging
from .util.returncode import compute_returncode
from .util.time import hhmmss

if TYPE_CHECKING:
    from .config.argparsing import Parser
    from .testcase import TestCase
    from .workspace import Workspace


logger = logging.get_logger(__name__)


def canary_runtests(runner: "Runner") -> None:
    pm = config.pluginmanager.hook
    try:
        logger.info(f"@*{{Starting}} session {runner.session}")
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
            f"@*{{Finished}} session in {(runner.finish - runner.start):.2f} s. "
            f"with returncode {runner.returncode}"
        )
        pm.canary_runtests_report(runner=runner)
    return


@dataclasses.dataclass
class Runner:
    cases: list["TestCase"]
    session: str
    workspace: "Workspace"
    _returncode: int = -20
    start: float = dataclasses.field(default=-1.0, init=False)
    finish: float = dataclasses.field(default=-1.0, init=False)

    @property
    def returncode(self) -> int:
        if self._returncode == -20:
            self._returncode = compute_returncode(self.cases)
        return self._returncode

    @contextmanager
    def timeit(self) -> Generator[None, None, None]:
        try:
            self.start = time.time()
            yield
        finally:
            self.finish = time.time()


@hookimpl(wrapper=True)
def canary_runteststart(case: "TestCase") -> Generator[None, None, bool]:
    case.workspace.create(exist_ok=True)
    if not config.getoption("dont_restage"):
        case.setup()
    yield
    case.save()
    return True


@hookimpl(wrapper=True)
def canary_runtest(case: "TestCase", queue: Queue) -> Generator[None, None, bool]:
    case.run(queue)
    yield
    case.save()
    return True


@hookimpl(wrapper=True)
def canary_runtest_finish(case: "TestCase") -> Generator[None, None, bool]:
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
    """Return a summary of the completed test cases.  if ``include_pass is True``, include
    passed tests in the summary

    """
    if not config.get("debug") or config.getoption("no_summary"):
        return
    include_pass = False
    truncate = 10
    file = io.StringIO()
    if not runner.cases:
        file.write("Nothing to report\n")
    else:
        totals: dict[tuple[str, str], list["TestCase"]] = {}
        for case in runner.cases:
            key = (case.status.category, case.status.status)
            totals.setdefault(key, []).append(case)
        for key in totals:
            if not include_pass and key[0] == "PASS":
                continue
            n: int = 0
            for case in sorted(totals[key], key=lambda t: t.name):
                file.write(case.statline + "\n")
                n += 1
                if truncate > 0 and truncate == n:
                    file.write(f"... truncating summary to the first {truncate} entries.\n")
                    file.write("See [bold]canary status[/bold] for the full summary\n")
                    break
    string = file.getvalue()
    if string.strip():
        string = "\n[bold]Short test summary info[/bold]\n" + string
    rich.print(string)


@hookimpl(specname="canary_runtests_report")
def print_runtests_durations(runner: Runner) -> None:
    if N := config.getoption("durations"):
        return print_durations(runner.cases, N)


@hookimpl(specname="canary_runtests_report", trylast=True)
def runtests_footer(runner: Runner) -> None:
    """Return a short, high-level, summary of test results"""
    print_footer(runner, "Session done")


def print_footer(runner: "Runner", title: str) -> None:
    """Return a short, high-level, summary of test results"""
    duration = runner.finish - runner.start
    totals: dict[str, list["TestCase"]] = {}
    for case in runner.cases:
        totals.setdefault(case.status.category, []).append(case)
    N = len(runner.cases)
    summary = [f"[bold blue]{N} total[/bold blue]:"]
    for category in totals:
        n = len(totals[category])
        if n:
            color = Status.color_for_category[category]
            summary.append(f"[{color}]{n} {category.lower()}[/{color}]")
    emojis = [glyphs.sparkles, glyphs.collision, glyphs.highvolt]
    x, y = random.sample(emojis, 2)
    kwds = {
        "x": x,
        "y": y,
        "s": summary[0] + " " + ", ".join(summary[1:]),
        "t": hhmmss(None if duration < 0 else duration),
        "title": title,
    }
    rich.print("%(x)s%(x)s [bold]%(title)s[/bold] -- %(s)s in [bold]%(t)s[/bold]" % kwds)


def print_durations(cases: list["TestCase"], N: int) -> None:
    cases.sort(key=lambda x: x.timekeeper.duration)
    ix = list(range(len(cases)))
    if N > 0:
        ix = ix[-N:]
    kwds = {"t": glyphs.turtle, "N": N}
    fp = io.StringIO()
    fp.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
    for i in ix:
        duration = cases[i].timekeeper.duration
        if duration < 0:
            continue
        name = cases[i].display_name(style="rich")
        id = cases[i].id[:7]
        fp.write("  %6.2f   %s %s\n" % (duration, id, name))
    rich.print(fp.getvalue().strip())
