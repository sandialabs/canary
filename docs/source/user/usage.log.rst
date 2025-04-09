.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-log-files:

Inspecting log files
====================

Use :ref:`canary log<canary-log>` to view logs of test cases and batches:

.. command-output:: canary log -h

Test case logs
--------------

The output of each test is logged to ``<path>/canary-out.txt`` and can be viewed by

.. code-block:: console

    canary log /ID

where ``ID`` is the test ID that is printed by :ref:`canary status<basics-status>`.

Batch logs
----------

Similar to individual test cases, the output of each batch is logged and can be view by

.. code-block:: console

    canary log ^M:N

where ``M`` is the batch lot and ``N`` is the batch number within the lot.

.. note::

    ``canary log`` should be run inside of a test session by either navigating to the session's directory or by ``canary -C PATH``.
