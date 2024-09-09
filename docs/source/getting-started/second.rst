.. _getting-started-second:

A second test
=============

In this second example, the external program "``add.py``" adds two numbers and writes the result to the console's stdout.  The test executes the script, reads it output, and verifies correctness.

.. literalinclude:: /examples/basic/second.pyt
   :language: python

The ``add.py`` program:

.. literalinclude:: /examples/basic/add.py
   :language: python

This test introduces two new features:

* ``nvtest.directives.link``: links ``add.py`` into the execution directory (see :ref:`test-directives` for more directives); and
* ``nvtest.Executable``: creates a callable python wrapper around executable scripts.

To run the test, navigate to the examples folder and run:

.. command-output:: nvtest run -k second ./basic
    :cwd: /examples
    :extraargs: -rv -w
    :setup: rm -rf TestResults
