# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


from typing import Generator

from ... import config
from multiprocessing import Queue
from ...testspec import ExecutionPolicy
from ...testspec import PythonFilePolicy
from ...testspec import TestCase
from ...testspec import TestSpec
from ..hookspec import hookimpl


@hookimpl(wrapper=True)
def canary_testcase_setup(case: TestCase) -> Generator[None, None, bool]:
    if not config.getoption("dont_restage"):
        case.setup()
    yield
    case.save()
    return True


@hookimpl(wrapper=True)
def canary_testcase_run(case: TestCase, queue: Queue, qsize: int, qrank: int) -> Generator[None, None, bool]:
    case.run(queue)
    yield
    case.save()
    return True


@hookimpl(wrapper=True)
def canary_testcase_finish(case: TestCase) -> Generator[None, None, bool]:
    case.finish()
    yield
    case.save()
    return True


@hookimpl
def canary_testcase_execution_policy(spec: TestSpec) -> ExecutionPolicy | None:
    if spec.file.suffix in (".pyt", ".py", ".vvt"):
        return PythonFilePolicy()
    return None
