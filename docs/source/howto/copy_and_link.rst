.. _howto-copy-and-link:

How to copy and link resource files into the test execution directory
=====================================================================

Resources needed by tests can be copied and linked from their source locations to the executtion directory with the :ref:`nvtest.directives.copy<directive-copy>` and :ref:`nvtest.directives.link<directive-link>` directives, respectively, as shown in the following example:

.. literalinclude:: /examples/copy_and_link/test.pyt
    :language: python

.. command-output:: nvtest run ./copy_and_link
    :cwd: /examples
