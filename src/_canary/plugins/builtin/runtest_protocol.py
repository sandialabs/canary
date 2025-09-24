# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


from typing import Generator

from ... import config
from ...atc import AbstractTestCase
from ..hookspec import hookimpl


@hookimpl(wrapper=True, trylast=True)
def canary_testcase_setup(case: AbstractTestCase) -> Generator[None, None, bool]:
    if not config.getoption("dont_restage"):
        case.setup()
    yield
    case.save()
    return True


@hookimpl(wrapper=True, trylast=True)
def canary_testcase_run(
    case: AbstractTestCase, qsize: int, qrank: int
) -> Generator[None, None, bool]:
    case.run(qsize=qsize, qrank=qrank)
    yield
    case.save()
    return True


@hookimpl(wrapper=True, trylast=True)
def canary_testcase_finish(case: AbstractTestCase) -> Generator[None, None, bool]:
    case.finish()
    yield
    case.save()
    return True
