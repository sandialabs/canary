# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Canary exception hierarchy and custom ``sys.excepthook``.

Exit codes
----------
The module-level constants map outcome names to their integer exit codes so
that callers can use ``raise SystemExit(fail_exit_status)`` without importing
the full ``status`` module.

Exceptions
----------
All test-outcome exceptions derive from :class:`MyException`, which carries an
``exit_code`` attribute.  The custom ``excepthook`` installed at import time
propagates that code to the process exit status when an exception goes
uncaught.

:class:`FailFast` and :class:`StopExecution` are control-flow exceptions used
internally by the executor; they do not derive from :class:`MyException`.
"""

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
    """Base class for all Canary test-outcome exceptions.

    Subclasses set ``exit_code`` to the appropriate :class:`~_canary.status.Outcome`
    integer value so the custom ``excepthook`` can propagate it to the process.
    """

    exit_code = 1


def excepthook(exctype, value, trace):
    """If an exception is uncaught, propagate its ``exit_code`` to the process."""
    sys_excepthook(exctype, value, trace)
    if hasattr(exctype, "exit_code"):
        raise SystemExit(value.exit_code)


# Overwrite the builtin excepthook with our custom version that will set the
# correct exit code
sys.excepthook, sys_excepthook = excepthook, sys.excepthook


class ResourceUnsatisfiableError(Exception):
    """Raised when a job's resource requirements cannot be satisfied by the pool."""

    pass


class TestFailed(MyException):
    """Raised by a test script to signal an explicit failure (non-zero exit)."""

    exit_code = fail_exit_status


class TestDiffed(MyException):
    """Raised by a test script to signal that output differed from baseline."""

    exit_code = diff_exit_status


class TestSkipped(MyException):
    """Raised by a test script to signal that the test should be skipped."""

    exit_code = skip_exit_status


class TestTimedOut(MyException):
    """Raised by the executor watchdog when a job exceeds its timeout budget."""

    exit_code = timeout_exit_status


class FailFast(Exception):
    """Raised to abort the run immediately after one or more jobs fail.

    Carries the list of failed jobs so callers can report them.

    Args:
        failed: A single :class:`~_canary.job.Job` or an iterable of jobs that
            triggered the fail-fast condition.
    """

    def __init__(self, failed):
        try:
            self.failed = list(failed)
        except TypeError:
            self.failed = [failed]
        super().__init__(",".join(_.name for _ in self.failed))


class StopExecution(Exception):
    """Raised to halt execution with a specific exit code and message.

    Used by subcommands that need to exit cleanly with a non-zero status without
    printing a traceback.

    Args:
        message: Human-readable explanation of why execution was stopped.
        exit_code: The process exit code to return.
    """

    def __init__(self, message, exit_code):
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)
