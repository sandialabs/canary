.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _getting-started:

Getting started
===============

``canary`` identifies and executes tests defined from multiple sources.  Each test runs in its own execution directory, with the default location being ``./TestResults/<test-name>``, and return code captured.  A return code of ``0`` indicates ``success``, while any other return code indicates a failure of some kind.  Python files having a ``.pyt`` extension are the native test format which will be used in the examples.

.. note::

   If ``canary`` is not installed on your system, you can install it as:

   .. code-block:: console

      python3 -m venv venv
      source ./venv/bin/activate
      python3 -m pip install canary-wm

.. note::

   All of the examples in the documentation can be obtained by the ``canary fetch`` command:

   .. code-block:: console

      canary fetch examples

.. _getting-started-first:

A first test
------------

The test file ``first.pyt`` defines a function that adds two numbers and verifies it for correctness:

.. literalinclude:: /examples/basic/first/first.pyt
   :language: python

To run the test, navigate to the examples directory and run ``canary run -k first ./basic`` which tells ``canary`` to run tests found in the path ``./basic`` and to filter tests to include only those tests with the keyword ``first``:

.. command-output:: canary run -k first ./basic
    :cwd: /examples
    :setup: rm -rf TestResults

A test is considered to have successfully completed if its exit code is ``0``.  See :ref:`basics-status` for more details on test statuses.

.. note::

   This test uses an optional :ref:`keyword directive<directive-keywords>` to aid in identifying the test and is is used to :ref:`filter tests<usage-filter>` (``-k first`` on the command line).

Test execution was conducted within a "test session" -- a folder created to run the tests "out of source".  The default name of the test session is ``TestResults``.  Details of the session can be obtained by navigating to it and executing :ref:`canary status<canary-status>`:

.. command-output:: canary status
    :cwd: /examples/TestResults

By default, only failed tests appear in the output, which is why the output above shows only a summary of completed tests.  To see the results of each test in the session, including passed tests, pass ``-rA``:

.. command-output:: canary status -rA
    :cwd: /examples/TestResults

.. _getting-started-second:

.. note::

   ``canary run`` creates and executes tests in a folder named ``TestResults``.  If this folder exists, ``canary run`` will issue an error that a test session already exists.  To start a new test session, you can either move or delete ``TestResults`` manually, or instruct ``canary`` to remove it automatically by passing ``-w`` to ``canary run``.

A second test
-------------

In this second example, the external program "``add.py``" adds two numbers and writes the result to the console's stdout is tested.

.. literalinclude:: /examples/basic/second/add.py
   :language: python

In the test, ``add.py`` is linked to the execution directory, is executed, and output verified for correctness:

.. literalinclude:: /examples/basic/second/second.pyt
   :language: python

This test introduces two new features:

* :func:`canary.directives.link`: links ``add.py`` into the execution directory (see :ref:`test-directives` for more directives); and
* ``canary.Executable``: creates a callable wrapper around executable scripts.

To run the test, navigate to the examples folder and run:

.. command-output:: canary run -k second ./basic
    :cwd: /examples
    :setup: rm -rf TestResults

Inspecting test output
----------------------

When a test is run, its output is captured to the file ``canary-out.txt`` in its execution directory.  The :ref:`canary log<canary-log>` command can find and print the contents of this file to the console:

.. note::

   ``canary log`` must be run from within a test session either by ``cd``\ ing into the directory or passing the directory name to ``canary``\ 's ``-C`` flag

.. command-output:: canary -C TestResults log second
    :cwd: /examples
