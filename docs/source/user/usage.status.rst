.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-status:

.. command-output:: rm -rf TestResults .canary
    :cwd: /examples
    :silent:

Getting the status of a test session
====================================

After running a test session, ``canary status`` can show the status of the test session

.. command-output:: canary run .
    :cwd: /examples
    :returncode: 14
    :ellipsis: 0
    :setup: rm -rf .canary TestResults

.. command-output:: canary status
    :cwd: /examples

The tests displayed can be modified by the ``-r`` flag.  For instance, to display only the failed tests, pass ``-rf``:

.. command-output:: canary status -rf
    :cwd: /examples

The ``N`` slowest durations can be displayed by passing ``--durations=N``:

.. command-output:: canary status --durations=5
    :cwd: /examples

.. command-output:: rm -rf TestResults .canary
    :cwd: /examples
    :silent:
