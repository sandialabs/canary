.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _getting-started:

Getting started
===============

``canary`` identifies and executes tests defined from multiple sources.  Each test runs in its own execution directory and return code captured.  A return code of ``0`` indicates ``success``, while any other return code indicates a failure of some kind.  Python files having a ``.pyt`` extension are the native test format which will be used in the examples.

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

.. command-output:: canary -d run -k first ./basic/first
    :cwd: /examples
    :setup: rm -rf .canary TestResults

A test is considered to have successfully completed if its exit code is ``0``.  See :ref:`basics-status` for more details on test statuses.

.. note::

   This test uses an optional :ref:`keyword directive<directive-keywords>` to aid in identifying the test and is used to :ref:`filter tests<usage-filter>` (``-k first`` on the command line).

``canary`` creates an isolated workspace at the start of each run inside the ``.canary`` folder.  All inputs, intermediate files, and outputs are contained within the workspace.  Once test execution completes, a "view" of the most recent results is created in the ``TestResults`` directory.  Details of the latest results are seen by :ref:`canary status<canary-status>`:

.. command-output:: canary status
    :nocache:
    :cwd: /examples

By default, only failed tests appear in the output.  To see the results of each test in the session, including passed tests, pass ``-rA``:

.. command-output:: canary status -rA
    :nocache:
    :cwd: /examples

.. _getting-started-second:

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

.. command-output:: canary run -k second ./basic/second
    :cwd: /examples

Inspecting test output
----------------------

When a test is run, its output is captured to the file ``canary-out.txt`` in its execution directory.  The :ref:`canary log<canary-log>` command can find and print the contents of this file to the console:

.. command-output:: canary log second
    :cwd: /examples


.. command-output:: rm -rf .canary TestResults
    :silent:
    :cwd: /examples
