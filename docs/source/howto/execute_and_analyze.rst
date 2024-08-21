.. _howto-execute-and-analyze:

Write an execute and analyze test
=================================

An execute/analyze test is one that uses parameters to expand into multiple test instances, followed by a final test instance that analyzes the results.  The analyze test only runs after all the parameter tests are finished.

The addition of the ``nvtest.directives.analyze`` directive marks a test as an execute/analyze test and will create a separate test for performing the analysis.

Consider the following test file ``examples/execute_and_analyze/execute_and_analyze.pyt``

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :language: python
    :lines: 1-6

The dependency graph for this test is

.. command-output:: nvtest describe execute_and_analyze/execute_and_analyze.pyt
    :cwd: /examples

As can be seen, the test ``execute_and_analyze`` depends on ``execute_and_analyze[a=1]``, ``execute_and_analyze[a=2]``, and ``execute_and_analyze[a=3]``.  When the test is run, these "children" tests are run first and then ``execute_and_analyze``:

.. command-output:: nvtest run -d TestResults.ExecuteAndAnalyze ./execute_and_analyze
    :cwd: /examples
    :extraargs: -rv -w

The full example
----------------

Define separate functions for the "test" and "verification" portions of the test, as defined in the ``test`` and ``verify_parameterized_test`` functions below.

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 9-22
    :language: python

``verify_parameterized_test`` is intended to be called for each child test.

During the final analysis phase, the children tests are made available in the ``nvtest.test.instance.dependencies`` attribute as shown in the ``analyze`` function below:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 25-30
    :language: python

Finally, the ``ExecuteAndAnalyze`` object is used to set up the test to broker which functions are called during different phases of the test:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 33-42
    :language: python

Accessing dependency parameters
-------------------------------

Dependency parameters can be accessed directly from the analysis test instance's ``dependencies``, eg,

.. code-block:: python

    self = nvtest.get_instance()
    self.dependencies[0].parameters

Additionally, the parameters of dependencies are stored in the analyze test instance's ``parameters`` attribute.  Consider the following test:

.. literalinclude:: /examples/analyze_only/analyze_only.pyt
    :lines: 8-10
    :language: python

The parameters ``np``, ``a``, and ``b`` of each dependency can be accessed directly:

.. literalinclude:: /examples/analyze_only/analyze_only.pyt
    :lines: 31-33
    :language: python

The ordering of the parameters is guaranteed to be the same as the ordering the ``dependencies``.  Eg, ``self.dependencies[i].parameters.a == self.parameters.a[i]``.

Additionally, the full table of dependency parameters is accessible as:

.. literalinclude:: /examples/analyze_only/analyze_only.pyt
    :lines: 34-36
    :language: python
