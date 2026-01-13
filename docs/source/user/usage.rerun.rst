.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-rerun:

Rerunning tests
===============

Navigate to the test results directory and execute :ref:`canary run<canary-run>` to rerun tests:

.. code-block:: console

   canary -C TEST_RESULTS_DIR run [OPTIONS]


or

.. code-block:: console

   cd TEST_RESULTS_DIR
   canary run [OPTIONS]

where ``TEST_RESULTS_DIR`` is the test results directory.

By default, only tests that had previously not run will be rerun, unless the test is explicitly requested via keyowrd or other :ref:`filters <usage-filter>`.  Optionally, a ``PATH`` argument can be passed to the ``canary run`` invocation, causing ``canary`` to rerun only those tests that are in ``PATH`` and its children:

.. code-block:: console

   canary -C TEST_RESULTS_DIR run [OPTIONS] PATH

Filter tests based on previous status
-------------------------------------

In rerun mode, the previous test status is included implicitly as a test keyword which allows :ref:`filtering <usage-filter>` based on previous statuses.

Examples
--------

.. command-output:: canary run -d TestResults.Rerun ./status
    :cwd: /examples
    :returncode: 30
    :setup: rm -rf .canary TestResults.Rerun


Rerun all failed tests
~~~~~~~~~~~~~~~~~~~~~~

.. command-output:: canary -C TestResults.Rerun run -k 'not success'
    :cwd: /examples
    :setup: canary run -w -d TestResults.Rerun ./status
    :returncode: 30

Rerun only the diffed tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. command-output:: canary -C TestResults.Rerun run -k diff
    :cwd: /examples
    :returncode: 2
