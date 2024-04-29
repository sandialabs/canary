.. _howto-enable:

How to get enable/disable tests
===============================

Tests can be enabled and/or disabled using the :ref:`enable<directive-enable>` directive.  The following test will be run when the option ``-o enable`` is passed to ``nvtest run``, otherwise it will be skipped:

.. literalinclude:: /examples/enable/test.pyt
    :language: python

.. command-output:: nvtest run ./enable
    :returncode: 7
    :cwd: /examples

.. command-output:: nvtest run -o enable ./enable
    :cwd: /examples
