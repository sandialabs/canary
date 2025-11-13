# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


from multiprocessing import Queue
from typing import Generator

from ... import config
from ...testcase import TestCase
from ..hookspec import hookimpl


@hookimpl(wrapper=True)
def canary_testcase_setup(case: TestCase) -> Generator[None, None, bool]:
    if not config.getoption("dont_restage"):
        case.setup()
    yield
    case.save()
    return True


@hookimpl(wrapper=True)
def canary_testcase_run(
    case: TestCase, queue: Queue, qsize: int, qrank: int
) -> Generator[None, None, bool]:
    case.run(queue)
    yield
    case.save()
    return True


@hookimpl(wrapper=True)
def canary_testcase_finish(case: TestCase) -> Generator[None, None, bool]:
    case.finish()
    yield
    # FIXME: case.cache_last_run()
    case.save()
    return True
