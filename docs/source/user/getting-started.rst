.. _getting-started:

Getting started
===============

``nvtest`` finds and runs tests defined in Python files having a ``.pyt`` extension.  The tests are run in their own execution directory (default: ``./TestResults/<test-name>``), and return code captured.  A return code of ``0`` indicates ``success`` and any other return code indicates failure.

.. note::

   All of the examples can be found in the ``/examples`` directory of the ``nvtest`` repository.  If you don't have a copy of the examples, they can be obtained by cloning ``nvtest``:

   .. code-block:: console

      git clone https://cee-gitlab.sandia.gov/ascic-test-infra/nvtest

.. _getting-started-first:

A first test
------------

The test file ``first.pyt`` defines a function that adds two numbers and verifies it for correctness:

.. literalinclude:: /examples/basic/first/first.pyt
   :language: python

To run the test, navigate to the examples directory and run ``nvtest run -k first ./basic`` which tells ``nvtest`` to run tests found in the path ``./basic`` and to filter tests to include only those tests with the keyword ``first``:

.. command-output:: nvtest run -k first ./basic
    :cwd: /examples
    :extraargs: -w
    :setup: rm -rf TestResults

A test is considered to have successfully completed if its exit code is ``0``.  See :ref:`basics-status` for more details on test statuses.

.. note::

   This test uses an optional :ref:`keyword directive<directive-keywords>` to aid in identifying the test and is is used to :ref:`filter tests<usage-filter>` (``-k first`` on the command line).

Test execution was conducted within a "test session" -- a folder created to run the tests "out of source".  The default name of the test session is ``TestResults``.  Details of the session can be obtained by navigating to it and executing :ref:`nvtest status<nvtest-status>`:

.. command-output:: nvtest status
    :cwd: /examples/TestResults

By default, only failed tests appear in the output, which is why the output above shows only a summary of completed tests.  To see the results of each test in the session, including passed tests, pass ``-rA``:

.. command-output:: nvtest status -rA
    :cwd: /examples/TestResults

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

* :func:`nvtest.directives.link`: links ``add.py`` into the execution directory (see :ref:`test-directives` for more directives); and
* ``nvtest.Executable``: creates a callable wrapper around executable scripts.

To run the test, navigate to the examples folder and run:

.. command-output:: nvtest run -k second ./basic
    :cwd: /examples
    :extraargs: -rv -w
    :setup: rm -rf TestResults

Inspecting test output
----------------------

When a test is run, its output is captured to the file ``nvtest-out.txt`` in its execution directory.  The :ref:`nvtest log<nvtest-log>` command can find and print the contents of this file to the console:

.. note::

   ``nvtest log`` must be run from within a test session either by ``cd``\ ing into the directory or passing the directory name to ``nvtest``\ 's ``-C`` flag

.. command-output:: nvtest -C TestResults log second
    :cwd: /examples
