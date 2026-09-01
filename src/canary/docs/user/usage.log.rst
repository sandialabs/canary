.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-log-files:

Inspecting log files
====================

Use :ref:`canary log<canary-log>` to view logs of test cases:

.. doc-run::
   :script: [{"args": "canary log -h"}]

Test case logs
--------------

The output of each test is logged to ``<path>/canary-out.txt`` and can be viewed by

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./basic/first", "ellipsis": 0, "cwd": "examples"}, {"args": "canary log first", "cwd": "examples"}]

The argument to ``canary log`` can by a test name or ``ID`` (as printed by :ref:`canary status<basics-status>`).
