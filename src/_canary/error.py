# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Control-flow and infrastructure exceptions.

These are *not* test outcomes; they steer the executor and the CLI:

* :class:`StopExecution` -- halt cleanly with a specific exit code and message,
  no traceback (used by subcommands and the executor).
* :class:`FailFast` -- abort the run after one or more jobs fail, carrying the
  failed jobs for reporting.
* :class:`ResourceUnsatisfiableError` -- a job's resource request can never be
  met by the pool.

Test-outcome exceptions (``TestFailed``/``TestDiffed``/``TestSkipped``/
``TestTimedOut``) and the outcome ``excepthook`` live in
:mod:`_canary.core.error`.
"""

#: Exit code used when a run selects no tests (distinct from any test outcome).
notests_exit_status = 7


class ResourceUnsatisfiableError(Exception):
    """Raised when a job's resource requirements cannot be satisfied by the pool."""

    pass


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
