.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

A second test
=============

The test file
-------------

In this second example, the external program "``add.py``" adds two numbers and writes the result to the console's stdout:

.. literalinclude:: /examples/basic/second/second.pyt
   :language: python

In the test, ``add.py`` is linked to the execution directory, is executed, and output verified for correctness.

This test introduces two new features:

* :func:`canary.directives.link`: links ``add.py`` into the execution directory (see :ref:`test-directives` for more directives); and
* :class:`~_canary.util.executable.Executable`: creates a callable wrapper around executable scripts.

Running the test
----------------

To run the test, navigate to the examples folder and run:

.. command-output:: canary run -k second ./basic
    :cwd: /examples
    :nocache:
    :setup: rm -rf .canary TestResults

Here, the ``-k`` flag was used to select only the tests having the ``second`` keyword.

Inspecting test output
----------------------

When a test is run, its output is captured to the file ``canary-out.txt`` in its execution directory.  The :ref:`canary log<canary-log>` command can find and print the contents of this file to the console:

.. command-output:: canary log second
    :cwd: /examples
    :nocache:

Contents of add.py
------------------

.. literalinclude:: /examples/basic/second/add.py
   :language: python
