# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import shlex
import time
from typing import Any
from typing import Generator

from ... import config
from ...test.case import TestCase
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
    cmd = case.command()
    cmd_line = shlex.join(cmd)
    case.stdout.write(f"==> Running {case.display_name}\n")
    case.stdout.write(f"==> Working directory: {case.working_directory}\n")
    case.stdout.write(f"==> Execution directory: {case.execution_directory}\n")
    case.stdout.write(f"==> Command line: {cmd_line}\n")
    if timeoutx := config.getoption("timeout_multiplier"):
        case.stdout.write(f"==> Timeout multiplier: {timeoutx}\n")
    case.stdout.flush()
    start = time.monotonic()
    case.run(qsize=qsize, qrank=qrank)
    with working_dir(case.working_directory):
        res = yield
    duration = time.monotonic() - start
    case.stdout.write(
        f"==> Finished running {case.display_name} "
        f"in {duration} s. with exit code {case.returncode}\n"
    )
    case.stdout.flush()
    case.save()
    return res


@hookimpl(tryfirst=True, wrapper=True)
def canary_testcase_finish(case: TestCase) -> Generator[Any, Any, Any]:
    case.finish()
    with working_dir(case.working_directory):
        res = yield
    case.save()
    return res
