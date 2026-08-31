.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-log-files:

Inspecting log files
====================

Use :ref:`canary log<canary-log>` to view logs of test cases:

.. doc-run::
   :script: ["canary log -h"]

Test case logs
--------------

The output of each test is logged to ``<path>/canary-out.txt`` and can be viewed by

.. doc-run::
   :before_script: [copy-examples]
   :script: ["canary run ./basic/first", "canary log first"]
   :cwd: /examples
   :ellipsis: [0, null]

The argument to ``canary log`` can by a test name or ``ID`` (as printed by :ref:`canary status<basics-status>`).
