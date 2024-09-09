.. _getting-started-first:

A first test
============

In this first test, the test file ``first.pyt`` defines a function that adds two numbers and verifies it for correctness.

.. literalinclude:: /examples/basic/first.pyt
   :language: python

.. note::

   A ``.pyt`` file is simply a python file with a ``.pyt`` extension.

.. note::

   This test defines optional ``keywords`` directive that is used to :ref:`filter tests<howto-filter>`.

To run the test, navigate to the examples directory and run:

.. command-output:: nvtest run -k first ./basic
    :cwd: /examples
    :extraargs: -rv -w
    :setup: rm -rf TestResults

A test is considered to have successfully completed if its exit code is 0.  See :ref:`basics-status` for more details on test statuses.
