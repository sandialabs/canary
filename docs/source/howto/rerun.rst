.. _howto-rerun:

Rerun tests
===========

Navigate to the test results directory and execute :ref:`nvtest run<nvtest-run>` to rerun tests:

.. code-block:: console

   nvtest -C TEST_RESULTS_DIR run [OPTIONS]


or

.. code-block:: console

   cd TEST_RESULTS_DIR
   nvtest run [OPTIONS]

where ``TEST_RESULTS_DIR`` is the test results directory.

By default, only tests that had previously not run, or failed, will be rerun, ie, those tests having ``failed``, ``diffed``, ``timeout``, and ``cancelled`` :ref:`status <userguide-status>`.

Optionally, a ``PATH`` argument can be passed to the ``nvtest run`` invocation, causing ``nvtest`` to rerun only those tests that are in ``PATH`` and its children:

.. code-block:: console

   nvtest -C TEST_RESULTS_DIR run [OPTIONS] PATH

Filter tests based on previous status
-------------------------------------

In rerun mode, the previous test status is included implicitly as a test keyword which allows :ref:`filtering <howto-filter>` based on previous statuses.

Batch considerations
--------------------

When a test session is created in :ref:`batched mode <howto-run-batched>`, the batch arguments from the test session invocation are inherited in future reruns.

Examples
--------

.. command-output:: nvtest run -d TestResults.Rerun ./status
    :cwd: /examples
    :returncode: 30
    :extraargs: -rv -w


Rerun all failed tests
~~~~~~~~~~~~~~~~~~~~~~

.. command-output:: nvtest -C TestResults.Rerun run .
    :cwd: /examples
    :returncode: 30
    :extraargs: -rv

Rerun only the diffed tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. command-output:: nvtest -C TestResults.Rerun run -k diff
    :cwd: /examples
    :returncode: 2
    :extraargs: -rv
