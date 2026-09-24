# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Test-outcome exceptions and the outcome-propagating ``sys.excepthook``.

These are the exceptions a test script raises to signal its own result, plus
the executor watchdog's timeout signal.  Each derives from :class:`MyException`
and carries an ``exit_code`` drawn from :class:`~_canary.core.status.Outcome`.

Importing this module installs a custom ``sys.excepthook`` that propagates an
uncaught exception's ``exit_code`` to the process exit status.  The install is a
deliberate import-time side effect: ``_canary``/``canary`` import these names
eagerly so the hook is active for every test subprocess.

Control-flow and infrastructure exceptions (``StopExecution``, ``FailFast``,
``ResourceUnsatisfiableError``) are *not* here -- they live in
:mod:`_canary.error`, since they are executor/CLI concerns, not domain outcomes.
"""

import sys

from . import status

skip_exit_status = status.Outcome.SKIPPED.value
diff_exit_status = status.Outcome.DIFFED.value
fail_exit_status = status.Outcome.FAILED.value
timeout_exit_status = status.Outcome.TIMEOUT.value
exception_exit_status = status.Outcome.ERROR.value

del status


class MyException(Exception):
    """Base class for all Canary test-outcome exceptions.

    Subclasses set ``exit_code`` to the appropriate :class:`~_canary.core.status.Outcome`
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
