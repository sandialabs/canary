.. _howto-execute-and-analyze:

How to write an execute and analyze test
========================================

An execute/analyze test is one that uses parameters to expand into multiple test instances, followed by a final test instance that analyzes the results.  The analyze test only runs after all the parameter tests are finished.

The addition of the ``nvtest.directives.analyze`` directive marks a test as an execute/analyze test and will create a separate test for performing the analysis.

Consider the following test file ``examples/execute_and_analyze/test.pyt``

.. literalinclude:: /examples/execute_and_analyze/test.pyt
    :language: python
    :lines: 1-6

The dependency graph for this test is

.. command-output:: nvtest describe execute_and_analyze/test.pyt
    :cwd: /examples

As can be seen, the test ``test`` depends on ``test[a=1]``, ``test[a=2]``, and ``test[a=3]``.  When the test is run, these "children" tests are run first and then ``test``:

.. command-output:: nvtest run -d TestResults.ExecuteAndAnalyze ./execute_and_analyze
    :cwd: /examples

The full example
----------------

Define separate functions for the "test" and "verification" portions of the test, as defined in ``test`` and ``verify_parameterized_test`` below.

.. literalinclude:: /examples/execute_and_analyze/test.pyt
    :lines: 9-22
    :language: python

``verify_parameterized_test`` is intended to be called for each child test.

During the final analysis phase, the children tests are made available in the ``nvtest.test.instance.dependencies`` attribute as shown in the ``analyze`` function below:

.. literalinclude:: /examples/execute_and_analyze/test.pyt
    :lines: 25-30
    :language: python

Finally, the ``ExecuteAndAnalyze`` object is used to set up the test to broker which functions are called during different phases of the test:

.. literalinclude:: /examples/execute_and_analyze/test.pyt
    :lines: 33-42
    :language: python

Full test file
--------------

.. literalinclude:: /examples/execute_and_analyze/test.pyt
    :language: python
