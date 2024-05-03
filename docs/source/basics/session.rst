.. _nvtest-session:

The test session
================

When ``nvtest run [path [path...]]`` is executed, ``path`` is searched for test files, the test files are expanded into test cases, and each test case is run in a separate execution directory.  Each test case's execution directory is relative to the session's root directory (default: ``./TestResults``).

Phases of a test session
------------------------

A test session consists of the following phases:

:ref:`Discovery<discovery>`:
  Search for test scripts in ``path [path...]``

:ref:`Setup<setup>`:
  Order test scripts, create unique execution directories for each test, and
  copy/link necessary resources into the execution directory.

:ref:`Run<run>`:
  For each test, move to its execution directory and run the test script, first
  ensuring that dependencies have been satisfied.

Finish:
  Perform clean up actions, if any.

Test session execution
----------------------

We will use an example to demonstrate each phase of the testing process.  Consider the test file ``centered_space/test.py`` (described in more detail in :ref:`howto-centered-parameter-space`):

.. literalinclude:: /examples/centered_space/test.pyt
   :language: python
   :lines: 1-11

.. _discovery:

Discovery
.........

During discovery, test files are collected, ``parameterize`` statements expanded, and dependency links created:

.. command-output:: rm -rf TestResults
   :silent:

.. command-output:: nvtest run --until=discovery -k centered_space .
   :cwd: /examples
   :extraargs: -rv -w --no-header

This test expands into 9 individual parameterized tests and 1 unparameterized test with the other 9 tests as dependencies.

.. _setup:

Setup
.....

During setup, the actual test execution directories are made and test assets linked:

.. command-output:: rm -rf TestResults
   :silent:

.. command-output:: nvtest run --until=setup -k centered_space .
   :cwd: /examples
   :extraargs: -rv -w --no-header

.. code-block:: console

  $ ls .
  centered_space/   TestResults/

.. command-output:: nvtest tree ./TestResults
   :cwd: /examples
   :nocache:

Each test's execution directory has the following naming convention: ``[relpath/]testname.key1=val1.key2=val2...keyn=valn``.  ``relpath`` is the relative path from the search path ``path`` to the test file ``testname.pyt`` and the ``key``\ s are the name of the test cases parameters [if any] with associated ``val``\ s.  The test script is symbolically linked into the execution directory.

.. warning::

  The test directory naming scheme is an implementation detail and may change in the future.  Do not write tests that rely on this naming scheme.

.. _run:

Run
...

During test execution, ``nvtest`` navigates to each test directory and runs the script:

.. command-output:: rm -rf TestResults
   :silent:

.. command-output:: nvtest run -k centered_space .
   :cwd: /examples
   :extraargs: -rv -w --no-header
   :nocache:

.. command-output:: nvtest tree ./TestResults
   :cwd: /examples
   :nocache:

Note the output files (``output.json``) from each of the parameterized test cases.


.. note::

   Tests are run asynchronously to (by default) utilize all available resources.
