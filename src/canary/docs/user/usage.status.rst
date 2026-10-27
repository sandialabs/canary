.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-status:

Getting the status of a test session
====================================

After running a test session, ``canary status`` can show the status of the test session

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run .", "returns": 14, "cwd": "examples", "ellipsis": 0}, {"args": "canary status", "cwd": "examples"}]

The tests displayed can be modified by the ``-r`` flag.  For instance, to display only the failed tests, pass ``-rf``:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary run .", "returns": 14, "cwd": "examples"}]
   :script: [{"args": "canary status -rf", "cwd": "examples"}]

The ``N`` slowest durations can be displayed by passing ``--durations=N``:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary run .", "returns": 14, "cwd": "examples"}]
   :script: [{"args": "canary status --durations=5", "cwd": "examples"}]

Grouped failure triage
----------------------

For larger failing sessions, ``canary status --group`` prints the normal summary and
table, then adds a grouped root-cause view based on normalized log signatures.

Use it together with :ref:`canary query failures <intro-getting-help>` when you need
to quickly identify which failures are likely the same underlying problem.
