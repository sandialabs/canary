# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Test-session execution hooks and reporting.

This module contains Canary's default implementation of the test execution
phase.  A :class:`Runner` represents one session's runnable jobs and provides
session timing and return-code aggregation.  The public
:func:`canary_runtests` function drives the hook lifecycle for a session:

* ``canary_runtests_start``
* ``canary_runtests``
* ``canary_runtests_report``

The default ``canary_runtests`` hook implementation, :func:`default_runtests`,
executes jobs through :class:`~_canary.queue_executor.ResourceQueueExecutor`.
Jobs are placed into a :class:`~_canary.queue.ResourceQueue` backed by the
resource pool owned by ``config.resource_manager``.  Completed jobs are reported
back to the workspace via the executor listener mechanism so result persistence
and live view updates remain centralized in the parent process.

Individual job execution is handled by :class:`JobExecutor`, which runs the
per-job hook sequence:

* ``canary_runteststart``
* ``canary_runtest``
* ``canary_runtest_finish``

The module also provides the built-in per-job hook wrappers that call
``Job.setup()``, ``Job.run()``, and ``Job.finish()``, plus console reporting
hooks for short summaries, duration reporting, and the final session footer.

Alternative execution backends, such as HPC or Flux integrations, may override
the ``canary_runtests`` hook.  The default implementation is registered with
``trylast=True`` so plugin-provided runners can take precedence.
"""

import dataclasses
import io
import sys
import threading
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Generator

import rich

from . import config
from .hookspec import hookimpl
from .queue import ResourceQueue
from .util import glyphs
from .util import logging
from .util.multiprocessing import SimpleQueue
from .util.returncode import compute_returncode
from .util.time import hhmmss

if TYPE_CHECKING:
    from .config.argparsing import Parser
    from .job import Job
    from .status import Outcome
    from .workspace import Workspace


logger = logging.get_logger(__name__)
global_lock = threading.Lock()


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

    @property
    def cases(self) -> list["Job"]:
        return self.jobs


def canary_runtests(runner: Runner, listeners: list[Callable[..., None]] | None = None) -> None:
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
        logger.exception("Unhandled exception in canary_runtests")
        raise
    finally:
        logger.info(
            f"[bold]Finished[/] session in {(runner.finish - runner.start):.2f} s. "
            f"with returncode {runner.returncode}"
        )
        pm.canary_runtests_report(runner=runner)
    return


@hookimpl(trylast=True, specname="canary_runtests")
def default_runtests(runner: Runner) -> bool:
    """Run each test jobs in ``jobs``.

    Args:
      jobs: test jobs to run

    Returns:
      The session returncode (0 for success)

    """
    from .queue_executor import ResourceQueueExecutor

    try:
        rpool = config.resource_manager.get_pool()
        queue = ResourceQueue(lock=global_lock, resource_pool=rpool)
        queue.put(*runner.jobs)  # type: ignore
        queue.prepare()
    except Exception:
        logger.exception("Unable to create resource queue")
        raise
    executor = JobExecutor()
    max_workers = config.getoption("workers") or -1
    now = time.time()
    for job in runner.jobs:
        if job.timekeeper.opened < 0:
            job.timekeeper.open(at=now)
    with ResourceQueueExecutor(queue, executor, max_workers=max_workers) as ex:
        ex.add_listener(runner.workspace.testcase_done_callback)
        ex.run()
    return True


class JobExecutor:
    """Class for running ``AbstractJob``."""

    def __call__(self, job: "Job", queue: SimpleQueue, **kwargs: Any) -> None:
        from .status import Status

        def mark_broken(phase: str, e: Exception) -> None:
            r = f"{e.__class__.__name__}({', '.join(repr(_) for _ in e.args)})"
            job.status = Status.BROKEN(reason=r)
            logger.debug(f"Failed to {phase} {job}", exc_info=e)
            job.save()

        if job.timekeeper.launched < 0:
            now = time.time()
            job.timekeeper.launch(at=now)
        queue.put({"event": "job_launched", "timestamp": job.timekeeper.launched})
        try:
            config.pluginmanager.hook.canary_runteststart(case=job)
        except Exception as e:
            mark_broken("setup", e)
            return

        queue.put({"event": "job_started", "timestamp": time.time()})
        try:
            config.pluginmanager.hook.canary_runtest(case=job)
            if job.timekeeper.finished < 0:
                now = time.time()
                job.timekeeper.close(at=now)
        except Exception as e:
            mark_broken("run", e)
            return

        try:
            config.pluginmanager.hook.canary_runtest_finish(case=job)
        except Exception as e:
            logger.debug(f"Failed to teardown {job}", exc_info=e)
            return


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
        parser, "--no-summary", action="store_true", help="Disable summary [default: %(default)s]"
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


def print_footer(runner: Runner, title: str) -> None:
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
    jobs.sort(key=lambda x: x.timekeeper.running())
    ix = list(range(len(jobs)))
    if N > 0:
        ix = ix[-N:]
    kwds = {"t": glyphs.turtle, "N": N}
    fp = io.StringIO()
    fp.write("%(t)s%(t)s Slowest %(N)d durations %(t)s%(t)s\n" % kwds)
    for i in ix:
        duration = jobs[i].timekeeper.running()
        if duration < 0:
            continue
        name = jobs[i].display_name(style="rich")
        id = jobs[i].id[:7]
        fp.write("  %6.2f   %s %s\n" % (duration, id, name))
    rich.print(fp.getvalue().strip(), file=sys.stderr)
