.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

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
   :lines: 4-14

.. _discover:

Discover
........

During discovery test files are collected:

.. command-output:: canary run --no-header --until=discover -k centered_space .
   :cwd: /examples
   :setup: rm -rf TestResults

.. _lock:

Lock
....

During the ``lock`` stage, test files are :ref:`filtered <usage-filter>`, ``parameterize`` statements are expanded, and dependency links created:

.. command-output:: canary run --no-header --until=lock -k centered_space .
   :cwd: /examples
   :setup: rm -rf TestResults

.. _run:

Run
...

During test execution, ``canary`` navigates to each test directory and runs the script:

.. command-output:: canary run --no-header -k centered_space .
   :cwd: /examples
   :nocache:
   :setup: rm -rf TestResults

.. image:: /images/Session.png
   :align: center

.. note::

   The default behavior is to run cases asynchronously utilizing all available resources.  This behavior can be modified by ``--workers=N``. See :ref:`basics-resource`.
