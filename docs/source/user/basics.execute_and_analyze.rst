.. _basics-execute-and-analyze:

The execute and analyze pattern
===============================

The "execute and analyze" pattern is a collection of :ref:`test cases <basics-testcase>` consisting of

* a :ref:`test file's <basics-testfile>` parameterized instantiations; and
* the test file's base, unparameterized, case.

The base case runs only after all of the parameterized test cases are finished.

The "execute and analyze" pattern is enabled by adding ``nvtest.directives.execbase`` to the test file's directives.

.. note::

    In ``vvtest``, the name of this directive is ``analyze``

Consider the directives section of the test file ``examples/execute_and_analyze/execute_and_analyze.pyt``:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :language: python
    :lines: 1-7

The dependency graph for this test is

.. command-output:: nvtest describe execute_and_analyze/execute_and_analyze.pyt
    :cwd: /examples

As can be seen, the base case ``execute_and_analyze`` depends on ``execute_and_analyze[a=1]``, ``execute_and_analyze[a=2]``, and ``execute_and_analyze[a=3]``.  When the test is run, these "children" tests are run first and then the base case:

.. command-output:: nvtest run -d TestResults.ExecuteAndAnalyze ./execute_and_analyze
    :cwd: /examples
    :extraargs: -rv -w

Test execution phases
---------------------

To take advantage of the execute and analyze pattern, a test should define separate functions for the "test", "analyze", and "base" phases of test execution. For example, a test might define separate ``test`` and ``analyze_parameterized_test`` functions as below:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 10-22
    :language: python

The functions ``test`` and ``analyze_parameterized_test`` are intended to be called for each child test in the test and analyze phases, respectively.

For the final base case (in which the children tests are made available in the ``nvtest.test.instance.dependencies`` attribute) a test might define a function similar to ``analyze_base_case``:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 25-31
    :language: python

Finally, the ``ExecuteAndAnalyze`` object is used to set up the test to broker which functions are called during different phases of the test:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 34-38
    :language: python

The full example
----------------

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :language: python

Accessing dependency parameters
-------------------------------

Dependency parameters can be accessed directly from the base test instance's ``dependencies``, e.g.,

.. code-block:: python

    self = nvtest.get_instance()
    self.dependencies[0].parameters

or, in the base test instance's ``parameters`` attribute.  Consider the following test:

.. literalinclude:: /examples/analyze_only/analyze_only.pyt
    :lines: 7-9
    :language: python

The parameters ``np``, ``a``, and ``b`` of each dependency can be accessed directly:

.. literalinclude:: /examples/analyze_only/analyze_only.pyt
    :lines: 29-31
    :language: python

The ordering of the parameters is guaranteed to be the same as the ordering the ``dependencies``.  E.g., ``self.dependencies[i].parameters.a == self.parameters.a[i]``.

Additionally, a full table of dependency parameters is accessible via key entry into the ``parameters`` attribute, where the key is a tuple containing each individual parameter name, e.g.:

.. literalinclude:: /examples/analyze_only/analyze_only.pyt
    :lines: 32-39
    :language: python

Run only the analysis section of a test
---------------------------------------

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
