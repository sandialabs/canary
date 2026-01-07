# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import io
import os
from datetime import datetime
from typing import TYPE_CHECKING

from ... import config
from ...hookspec import hookimpl
from ...util import logging
from ...util.string import pluralize

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


@hookimpl(specname="canary_runtest")
def repeat_until_pass(case: "TestCase") -> None:
    if (case.status.category == "FAIL") and (count := config.getoption("repeat_until_pass")):
        i: int = 0
        while i < count:
            i += 1
            rerun_case(case, i)
            if case.status.category == "PASS":
                return
        logger.error(
            f"{case}: failed to finish successfully after {i} additional {pluralize('attempt', i)}"
        )


@hookimpl(specname="canary_runtest")
def repeat_after_timeout(case: "TestCase") -> None:
    if (case.status.status == "TIMEOUT") and (count := config.getoption("repeat_after_timeout")):
        i: int = 0
        while i < count:
            i += 1
            rerun_case(case, i)
            if not case.status.status == "TIMEOUT":
                return
        logger.error(
            f"{case}: failed to finish without timing out after {i} additional {pluralize('attempt', i)}"
        )


@hookimpl(specname="canary_runtest")
def repeat_until_fail(case: "TestCase") -> None:
    if (case.status.category == "PASS") and (count := config.getoption("repeat_until_fail")):
        i: int = 1
        while i < count:
            i += 1
            rerun_case(case, i)
            if not case.status.category == "PASS":
                break
        else:
            return
        n: int = count
        logger.error(
            f"{case}: failed to finish successfully {n} {pluralize('time', n)} without failing"
        )


def rerun_case(case: "TestCase", attempt: int) -> None:
    try:
        case.restore_workspace()
        if summary := job_start_summary(case):
            logger.debug(summary)
        case.setup()
        case.run()
    finally:
        if summary := job_finish_summary(case, attempt=attempt):
            logger.debug(summary)


def job_start_summary(case: "TestCase") -> str:
    if logging.get_level() > logging.INFO:
        return ""
    fmt = io.StringIO()
    if os.getenv("GITLAB_CI"):
        fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
    fmt.write("[bold]Repeating[/] %s: %s" % (case.id[:7], case.display_name(resolve=True)))
    return fmt.getvalue().strip()


def job_finish_summary(case: "TestCase", *, attempt: int) -> str:
    if logging.get_level() > logging.INFO:
        return ""
    fmt = io.StringIO()
    if os.getenv("GITLAB_CI"):
        fmt.write(datetime.now().strftime("[%Y.%m.%d %H:%M:%S]") + " ")
    fmt.write(
        f"[bold]Finished[/] %s (attempt {attempt + 1}): %s %s"
        % (case.id[:7], case.display_name(resolve=True), case.status.display_name())
    )
    return fmt.getvalue().strip()
