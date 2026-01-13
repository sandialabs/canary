.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-status:

Getting the status of a test session
====================================

After running a test session, the ``status`` subcommand can show the status of the test session

.. command-output:: canary run .
    :cwd: /examples
    :returncode: 30
    :ellipsis: 0
    :setup: rm -rf .canary TestResults

.. command-output:: canary -C TestResults status .
    :cwd: /examples

.. note::

    ``canary status`` should be run inside of a test session by either navigating to the session's directory or by ``canary -C PATH``.

The tests displayed can be modified by the ``-r`` flag.  For instance, to display only the failed tests, pass ``-rf``:

.. command-output:: canary -C TestResults status -rf .
    :cwd: /examples

The ``N`` slowest durations can be displayed by passing ``--durations=N``:

.. command-output:: canary -C TestResults status --durations=5 .
    :cwd: /examples
