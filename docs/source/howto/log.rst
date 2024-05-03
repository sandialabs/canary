.. _howto-log-files:

Inspect log files
=================

Use :ref:`nvtest log<nvtest-log>` to view logs of test cases and batches:

.. command-output:: nvtest log -h

Test case logs
--------------

The output of each test is logged to ``<path>/nvtest-out.txt`` and can be viewed by

.. code-block:: console

    nvtest log /ID

where ``ID`` is the test ID that is printed by :ref:`nvtest status<howto-status>`.

Batch logs
----------

Similar to individual test cases, the output of each batch is logged and can be view by

.. code-block:: console

    nvtest log ^N

where ``N`` is the batch number.

.. note::

    ``nvtest log`` should be run inside of a test session by either navigating to the session's directory or by ``nvtest -C PATH``.
