.. _userguide-session:

The test session
================

When ``nvtest run [path [path...]]`` is executed, ``path`` is searched for test files, the test files are expanded into test cases, and each test case is run in a separate execution directory.  Each test case's execution directory is relative to the session's root directory (default: ``./TestResults``).

Phases of a test session
------------------------

A test session consists of the following phases:

:ref:`Discover<discover>`:
  Search ``path [path...]`` for test scripts.

:ref:`Freeze<freeze>`:
  "Freeze" test files into test cases based on :ref:`filtering<howto-filter>` criteria and
  :ref:`parameterizations<howto-parameterize>`.

:ref:`Populate<populate>`:
  Create unique execution directories for each test case and :ref:`copy/link <howto-copy-and-link>` necessary resources into the execution directory.

:ref:`Batch<batch>`:
  For :ref:`batched<howto-run-batched>` sessions, group test cases into batches to run in a scheduler.

:ref:`Run<run>`:
  For each test, move into its execution directory and run the test script (after each dependency has completed).

Finish:
  Perform clean up actions, if any.

Test session execution
----------------------

We will use an example to demonstrate each phase of the testing process.  Consider the test file ``centered_space/test.py`` (described in more detail in :ref:`howto-centered-parameter-space`):

.. literalinclude:: /examples/centered_space/centered_space.pyt
   :language: python
   :lines: 1-11

.. _discover:

Discover
........

During discovery test files are collected:

.. command-output:: nvtest run --until=discover -k centered_space .
   :cwd: /examples
   :extraargs: -rv -w --no-header
   :setup: rm -rf TestResults

.. _freeze:

Freeze
......

During the ``freeze`` stage, test files are :ref:`filtered <howto-filter>`, ``parameterize`` statements are expanded, and dependency links created:

.. command-output:: nvtest run --until=freeze -k centered_space .
   :cwd: /examples
   :extraargs: -rv -w --no-header
   :setup: rm -rf TestResults

.. _populate:

Populate
........

During the ``populate`` stage, the test execution directories are made and populated with test assets:

.. command-output:: nvtest run --until=populate -k centered_space .
   :cwd: /examples
   :extraargs: -rv -w
   :setup: rm -rf TestResults

.. code-block:: console

  $ ls .
  centered_space/   TestResults/

.. command-output:: nvtest tree ./TestResults
   :cwd: /examples
   :nocache:

Each test's execution directory has the following naming convention: ``[relpath/]testname[.key=val[...]]``.  ``relpath`` is the relative path from the search path root to the test file ``testname.pyt`` and the ``key``\ s are the name of the test cases parameters (if any) with associated ``val``\ s.  The test script is symbolically linked into the execution directory.

.. warning::

  The test directory naming scheme is an implementation detail and may change in the future.  Do not write tests that rely on this naming scheme.

.. _batch:

Batch
.....

Group test cases into batches to run in a scheduler.  The default batching scheme is to:

1. group cases by the number of compute nodes required to run; and
2. partition each group into batches that complete in a set time (defined by the ``-b length=T`` option)

Optionally, a fixed number of batches can be requested (``-b count=N``).

.. _run:

Run
...

During test execution, ``nvtest`` navigates to each test directory and runs the script:

.. command-output:: nvtest run -k centered_space .
   :cwd: /examples
   :extraargs: -rv -w --no-header
   :nocache:
   :setup: rm -rf TestResults

.. command-output:: nvtest tree ./TestResults
   :cwd: /examples
   :nocache:

Note the output files (``output.json``) from each of the parameterized test cases.


.. note::

   The default behavior is to run cases asynchronously utilizing all available resources.  This behavior can be modified by the ``-l scope:type:X`` option.  See :ref:`userguide-resource`.
