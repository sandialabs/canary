.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-status:

Getting the status of a test session
====================================

After running a test session, ``canary status`` can show the status of the test session

.. doc-run::
   :before_script: [copy-examples]
   :script: ["canary run .", "canary status"]
   :cwd: /examples
   :returncode: [14, 0]
   :ellipsis: [0, null]

The tests displayed can be modified by the ``-r`` flag.  For instance, to display only the failed tests, pass ``-rf``:

.. doc-run::
   :before_script: [copy-examples, "canary run . || true"]
   :script: ["canary status -rf"]
   :cwd: /examples
   :shell:

The ``N`` slowest durations can be displayed by passing ``--durations=N``:

.. doc-run::
   :before_script: [copy-examples, "canary run . || true"]
   :script: ["canary status --durations=5"]
   :cwd: /examples
   :shell:
