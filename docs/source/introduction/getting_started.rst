Getting started
===============

A first test
------------

In this first test, the test file ``first.pyt`` defines a function that adds two numbers and verifies it for correctness.

.. literalinclude:: /examples/basic/first.pyt
   :language: python

.. note::

   A ``.pyt`` file is simply a python file with a ``.pyt`` extension.

.. note::

   This test defines optional ``keywords`` that can be used to :ref:`filter tests<howto-filter>`.

To run the test, navigate to the examples directory and run:

.. command-output:: nvtest run -k first ./basic
   :cwd: /examples

A test is considered to have successfully completed if its exit code is 0.  See :ref:`test-status` for more details on test statuses.

A second test
-------------

In this second example, the external program "``add.py``" adds two numbers and writes the result to the console's stdout.  The test executes the script, reads it output, and verifies correctness.

.. literalinclude:: /examples/basic/second.pyt
   :language: python

The program script:

.. literalinclude:: /examples/basic/add.py
   :language: python

This test introduces two new features:

* ``nvtest.directives.link``: links ``add.py`` into the execution directory (see :ref:`test-directives` for more directives); and
* ``nvtest.Executable``: creates a callable python wrapper around executable scripts.

To run the test, navigate to the examples folder and run:

.. command-output:: nvtest run -k second ./basic
   :cwd: /examples
