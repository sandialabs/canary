.. _basics-copy-and-link:

Copying and linking resource files into the test execution directory
====================================================================

Resources needed by tests can be copied and linked from their source locations to the execution directory with the :ref:`nvtest.directives.copy<directive-copy>` and :ref:`nvtest.directives.link<directive-link>` directives, respectively, as shown in the following example:

.. literalinclude:: /examples/copy_and_link/copy_and_link.pyt
    :language: python

.. command-output:: nvtest run -d TestResults.CopyAndLink ./copy_and_link
    :cwd: /examples
    :extraargs: -rv -w
