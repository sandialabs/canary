.. _howto-analyze:

Run only the analysis section of a test
=======================================

After a test is run, the analysis sections can be run with the :ref:`nvtest analyze<nvtest-analyze>` command.  Consider the test introduced in :ref:`basics-execute-and-analyze`, repeated here for convenience:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :language: python

After the test has been run, the analysis sections can be run without rerunning the (potentially expensive) test portion:

.. command-output:: nvtest run -d TestResults.ExecuteAndAnalyze ./execute_and_analyze
    :cwd: /examples
    :extraargs: -rv -w
    :ellipsis: 0


.. command-output:: nvtest -C TestResults.ExecuteAndAnalyze analyze .
    :cwd: /examples
