Getting started
===============

A first test
------------

In this first test, the test file ``first.pyt`` defines a function that adds two numbers and verifies it for correctness.

.. literalinclude:: /examples/basic/first.pyt
   :language: python

To run the test, navigate to the directory containing ``first.pyt`` and run the command

.. command-output:: nvtest run -k first .
   :cwd: /examples/basic

.. note::

   This test defines optional ``keywords`` that can be used to :ref:`filter tests<howto-filter>`.

A second test
-------------

In this second example, the external program "``add.py``" adds two numbers and writes the result to the console's stdout.  The test executes the script, reads it output, and verifies correctness.

.. literalinclude:: /examples/basic/second.pyt
   :language: python

The test script:

.. literalinclude:: /examples/basic/add.py
   :language: python

This test introduces two new features:

* ``nvtest.directives.link`` links ``add`` into the execution directory (see :ref:`test-directives` for more directives); and
* ``nvtest.Executable`` which provides a wrapper around executable scripts.

To run the test, navigate to the folder containing the script and test file and run the command:

.. command-output:: nvtest run -k second .
   :cwd: /examples/basic
