.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-basic-second:

A second test
=============

This example introduces two common patterns:

* staging an input file into the test working directory with :func:`canary.directives.link`; and
* running an external program using :class:`~_canary.util.executable.Executable`.

The test file
-------------

In this example, the external program ``add.py`` adds two numbers and prints the result to
standard output. The test links ``add.py`` into the working directory, executes it, and checks the
output for correctness:

.. literalinclude:: /examples/basic/second/second.pyt
   :language: python

Running the test
----------------

From the ``examples`` directory, run only tests with the ``second`` keyword:

.. command-output:: canary run -k second ./basic
    :cwd: /examples
    :nocache:
    :setup: rm -rf .canary TestResults

Here, ``-k`` filters the session to tests matching the given keyword expression.

Inspecting test output
----------------------

When a test runs, its captured console output is written to ``canary-out.txt`` in the test’s
working directory. The :ref:`canary log <canary-log>` command locates and prints that file:

.. command-output:: canary log second
    :cwd: /examples
    :nocache:

Contents of ``add.py``
----------------------

.. literalinclude:: /examples/basic/second/add.py
   :language: python


.. program-output:: rm -rf .canary TestResults
    :silent:
    :nocache:
    :cwd: /examples
