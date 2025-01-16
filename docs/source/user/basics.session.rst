.. _basics-session:

The test session
================

When ``canary run [options] path [path...]`` is executed, ``path`` is searched for :ref:`test files<basics-testfile>`, the test files are expanded into test cases, and each test case is run in a separate execution directory, relative to the session's root directory (default: ``./TestResults``).

Phases of a test session
------------------------

A test session consists of the following phases:

:ref:`Discover<discover>`:
  Search ``path [path...]`` for test scripts.

:ref:`Lock<lock>`:
  "Lock" test files into test cases based on :ref:`filtering<usage-filter>` criteria and
  :ref:`parameterizations<usage-parameterize>`.

:ref:`Batch<batch>`:
  For :ref:`batched<usage-run-batched>` sessions, group test cases into batches to run in a batch runner.

:ref:`Run<run>`:
  For each test, move into its execution directory and run the test script (after each dependency has completed, if necessary).

Finish:
  Perform clean up actions, if any.

.. image:: /dot/Flow.png
   :align: center
   :scale: 50 %

Test session execution
----------------------

We will use an example to demonstrate each phase of the testing process.  Consider the test file ``centered_space/test.py`` (described in more detail in :ref:`centered-parameter-space`):

.. literalinclude:: /examples/centered_space/centered_space.pyt
   :language: python
   :lines: 1-11

.. _discover:

Discover
........

During discovery test files are collected:

.. command-output:: canary run --until=discover -k centered_space .
   :cwd: /examples
   :extraargs: -rv -w --no-header
   :setup: rm -rf TestResults

.. _lock:

Lock
....

During the ``lock`` stage, test files are :ref:`filtered <usage-filter>`, ``parameterize`` statements are expanded, and dependency links created:

.. command-output:: canary run --until=lock -k centered_space .
   :cwd: /examples
   :extraargs: -rv -w --no-header
   :setup: rm -rf TestResults

.. _batch:

Batch
.....

[Optional] Group test cases into batches to run in a batch runner.  The default batching scheme is to:

1. group cases by the number of compute nodes required to run; and
2. partition each group into batches that complete in a set time (defined by the ``-b length=T`` option).

.. note::

   A test is always batched with tests requiring the same node count.

Optionally, a fixed number of batches can be requested (``-b count=N``).

.. _run:

Run
...

During test execution, ``canary`` navigates to each test directory and runs the script:

.. command-output:: canary run -k centered_space .
   :cwd: /examples
   :extraargs: -rv -w --no-header
   :nocache:
   :setup: rm -rf TestResults

.. image:: /images/Session.png
   :align: center

.. note::

   The default behavior is to run cases asynchronously utilizing all available resources.  This behavior can be modified by ``--workers=N``. See :ref:`basics-resource`.
