from typing import TYPE_CHECKING

from ... import config
from ...testcase import TestCase
from ...util import logging
from ...util.string import pluralize
from ..hookspec import hookimpl

if TYPE_CHECKING:
    from ...config.argparsing import Parser


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
def repeat_until_pass(case: TestCase, qsize: int, qrank: int) -> None:
    if case.status.satisfies("failed") and (count := config.getoption("repeat_until_pass")):
        i: int = 0
        while i < count:
            i += 1
            case.reset()
            case.run(qsize=qsize, qrank=qrank, repeat=True)
            if not case.status.satisfies("failed"):
                return
        n: int = i - 1
        logging.error(
            f"{case}: failed to finish successfully after {i} additional {pluralize('attempt', i)}"
        )


@hookimpl(specname="canary_testcase_run")
def repeat_after_timeout(case: TestCase, qsize: int, qrank: int) -> None:
    if case.status.satisfies("timeout") and (count := config.getoption("repeat_after_timeout")):
        i: int = 0
        while i < count:
            i += 1
            case.reset()
            case.run(qsize=qsize, qrank=qrank, attempt=i)
            if not case.status.satisfies("timeout"):
                return
        logging.error(
            f"{case}: failed to finish without timing out after {i} additional {pluralize('attempt', i)}"
        )


@hookimpl(specname="canary_testcase_run")
def repeat_until_fail(case: TestCase, qsize: int, qrank: int) -> None:
    if case.status.satisfies("success") and (count := config.getoption("repeat_until_fail")):
        i: int = 1
        while i < count:
            i += 1
            case.reset()
            case.run(qsize=qsize, qrank=qrank, attempt=i)
            if not case.status.satisfies("success"):
                break
        else:
            return
        n: int = count
        logging.error(
            f"{case}: failed to finish successfully {n} {pluralize('time', n)} without failing"
        )
