.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-log-files:

Inspecting log files
====================

Use :ref:`canary log<canary-log>` to view logs of test cases:

.. command-output:: canary log -h

Test case logs
--------------

The output of each test is logged to ``<path>/canary-out.txt`` and can be viewed by

.. code-block:: console

    canary log /ID

where ``ID`` is the test ID that is printed by :ref:`canary status<basics-status>`.
