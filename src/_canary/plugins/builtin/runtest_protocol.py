# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any
from typing import Generator

from ... import config
from ...testcase import TestCase
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


@hookimpl(tryfirst=True, wrapper=True)
def canary_testcase_finish(case: TestCase) -> Generator[Any, Any, Any]:
    case.finish()
    with working_dir(case.working_directory):
        res = yield
    case.save()
    return res
