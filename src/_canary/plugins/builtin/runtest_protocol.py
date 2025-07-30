# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any
from typing import Generator

from ... import config
from ...testcase import TestCase
from ...util import logging
from ...util.filesystem import working_dir
from ..hookspec import hookimpl


@hookimpl(tryfirst=True, wrapper=True)
def canary_testcase_setup(case: TestCase) -> Generator[Any, Any, Any]:
    if not config.getoption("dont_restage"):
        case.setup()
    with working_dir(case.working_directory):
        res = yield
    case.save()
    return res


@hookimpl(tryfirst=True, wrapper=True)
def canary_testcase_run(case: TestCase, qsize: int, qrank: int) -> Generator[Any, Any, Any]:
    case.run(qsize=qsize, qrank=qrank)
    with working_dir(case.working_directory):
        res = yield
    case.save()
    return res


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
        logging.error(f"{case}: failed to finish successfully after {i} attempts")


@hookimpl(specname="canary_testcase_run")
def repeat_after_timeout(case: TestCase, qsize: int, qrank: int) -> None:
    if case.status.satisfies("timeout") and (count := config.getoption("repeat_after_timeout")):
        i: int = 0
        while i < count:
            i += 1
            case.reset()
            case.run(qsize=qsize, qrank=qrank, repeat=True)
            if not case.status.satisfies("timeout"):
                return
        logging.error(f"{case}: failed to finish without timing out in {i} attempts")


@hookimpl(specname="canary_testcase_run")
def repeat_until_fail(case: TestCase, qsize: int, qrank: int) -> None:
    if case.status.satisfies("success") and (count := config.getoption("repeat_until_fail")):
        i: int = 1
        while i < count:
            i += 1
            case.reset()
            case.run(qsize=qsize, qrank=qrank, repeat=True)
            if not case.status.satisfies("success"):
                break
        else:
            return
        logging.error(f"{case}: failed to finish successfully {count} times without failing")


@hookimpl(tryfirst=True, wrapper=True)
def canary_testcase_finish(case: TestCase) -> Generator[Any, Any, Any]:
    case.finish()
    with working_dir(case.working_directory):
        res = yield
    case.save()
    return res
