import io
import multiprocessing as mp
import os
from datetime import datetime
from typing import TYPE_CHECKING

from ... import config
from ...util import logging
from ...util.misc import digits
from ...util.string import pluralize
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config.argparsing import Parser
    from ...testcase import TestCase

logger = logging.get_logger(__name__)


@hookimpl
def canary_addoption(parser: "Parser") -> None:
    group = "repeat"
    parser.add_argument(
        "--repeat-until-pass",
        type=int,
        command="run",
        group=group,
        help="Allow each test to run up to <n> times in order to pass",
    )
    parser.add_argument(
        "--repeat-after-timeout",
        type=int,
        command="run",
        group=group,
        help="Allow each test to run up to <n> times if it times out",
    )
    parser.add_argument(
        "--repeat-until-fail",
        type=int,
        command="run",
        group=group,
        help="Require each test to run <n> times without failing in order to pass",
    )


@hookimpl(specname="canary_testcase_run")
def repeat_until_pass(case: "TestCase", queue: mp.Queue, qsize: int, qrank: int) -> None:
    if (case.status.name == "FAILED") and (count := config.getoption("repeat_until_pass")):
        i: int = 0
        while i < count:
            i += 1
            rerun_case(case, queue, qsize, qrank, i)
            if case.status.name == "SUCCESS":
                return
        logger.error(
            f"{case}: failed to finish successfully after {i} additional {pluralize('attempt', i)}"
        )


@hookimpl(specname="canary_testcase_run")
def repeat_after_timeout(case: "TestCase", queue: mp.Queue, qsize: int, qrank: int) -> None:
    if (case.status.name == "TIMEOUT") and (count := config.getoption("repeat_after_timeout")):
        i: int = 0
        while i < count:
            i += 1
            rerun_case(case, queue, qsize, qrank, i)
            if not case.status.name == "TIMEOUT":
                return
        logger.error(
            f"{case}: failed to finish without timing out after {i} additional {pluralize('attempt', i)}"
        )


@hookimpl(specname="canary_testcase_run")
def repeat_until_fail(case: "TestCase", queue: mp.Queue, qsize: int, qrank: int) -> None:
    if (case.status.name == "SUCCESS") and (count := config.getoption("repeat_until_fail")):
        i: int = 1
        while i < count:
            i += 1
            rerun_case(case, queue, qsize, qrank, i)
            if not case.status.name == "SUCCESS":
                break
        else:
            return
        n: int = count
        logger.error(
            f"{case}: failed to finish successfully {n} {pluralize('time', n)} without failing"
        )


def rerun_case(case: "TestCase", queue: mp.Queue, qsize: int, qrank: int, attempt: int) -> None:
    dont_restage = config.getoption("dont_restage")
    try:
        case.restore_workspace()
        if summary := job_start_summary(case, qsize=qsize, qrank=qrank):
            logger.log(logging.EMIT, summary, extra={"prefix": ""})
        case.setup()
        case.run(queue=queue)
    finally:
        if summary := job_finish_summary(case, qsize=qsize, qrank=qrank, attempt=attempt):
            logger.log(logging.EMIT, summary, extra={"prefix": ""})
        if dont_restage:
            config.options.dont_restage = dont_restage


def job_start_summary(case: "TestCase", qrank: int | None, qsize: int | None) -> str:
    if config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO:
        return ""
    fmt = io.StringIO()
    if os.getenv("GITLAB_CI"):
        fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
    if qrank is not None and qsize is not None:
        fmt.write("@*{[%s]} " % f"{qrank + 1:0{digits(qsize)}}/{qsize}")
    fmt.write("Repeating @*b{%s}: %s" % (case.id[:7], case.spec.fullname))
    return fmt.getvalue().strip()


def job_finish_summary(
    case: "TestCase", *, qrank: int | None, qsize: int | None, attempt: int
) -> str:
    if config.getoption("format") == "progress-bar" or logging.get_level() > logging.INFO:
        return ""
    fmt = io.StringIO()
    if os.getenv("GITLAB_CI"):
        fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
    if qrank is not None and qsize is not None:
        fmt.write("@*{[%s]} " % f"{qrank + 1:0{digits(qsize)}}/{qsize}")
    fmt.write(
        f"Finished @*b{{%s}} (attempt {attempt + 1}): %s %s"
        % (case.id[:7], case.fullname, case.status.cname)
    )
    return fmt.getvalue().strip()
