.. _howto-analyze:

How to run only the analysis section of a test
==============================================

After a test is run, the analysis sections can be run with the ``nvtest analyze``
command.  Consider the following test

.. literalinclude:: /examples/execute_and_analyze/test.pyt
    :language: python

To execute, first run the tests.  Then, navigate to the test directory and run

.. program-output:: nvtest run -vw -d ExecuteAndAnalyze ./execute_and_analyze
    :cwd: /examples


.. program-output:: nvtest -C ExecuteAndAnalyze analyze .
    :cwd: /examples
