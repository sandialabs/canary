.. _usage-enable:

Enabling/disabling tests
========================

Tests can be enabled and/or disabled using the :ref:`enable<directive-enable>` directive.  The following test will be run when the option ``-o enable`` is passed to ``nvtest run``, otherwise it will be skipped:

.. literalinclude:: /examples/enable/enable.pyt
    :language: python

.. command-output:: nvtest run -d TestResults.Enable ./enable
    :extraargs: -rv -w
    :returncode: 7
    :cwd: /examples

.. command-output:: nvtest run -d TestResults.Enable -o enable ./enable
    :extraargs: -rv -w
    :cwd: /examples
