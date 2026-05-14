# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import sys

from . import status

skip_exit_status = status.Outcome.SKIPPED.value
diff_exit_status = status.Outcome.DIFFED.value
fail_exit_status = status.Outcome.FAILED.value
timeout_exit_status = status.Outcome.TIMEOUT.value
exception_exit_status = status.Outcome.ERROR.value
notests_exit_status = 7

del status


class MyException(Exception):
    exit_code = 1


def excepthook(exctype, value, trace):
    """If an exeception is uncaught, set the proper exit code"""
    sys_excepthook(exctype, value, trace)
    if hasattr(exctype, "exit_code"):
        raise SystemExit(value.exit_code)


# Overwrite the builtin excepthook with our custom version that will set the
# correct exit code
sys.excepthook, sys_excepthook = excepthook, sys.excepthook


class ResourceUnsatisfiableError(Exception):
    pass


class TestFailed(MyException):
    exit_code = fail_exit_status


class TestDiffed(MyException):
    exit_code = diff_exit_status


class TestSkipped(MyException):
    exit_code = skip_exit_status


class TestTimedOut(MyException):
    exit_code = timeout_exit_status


class FailFast(Exception):
    def __init__(self, failed):
        try:
            self.failed = list(failed)
        except TypeError:
            self.failed = [failed]
        super().__init__(",".join(_.name for _ in self.failed))


class StopExecution(Exception):
    def __init__(self, message, exit_code):
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)
