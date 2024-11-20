.. _usage-execute-and-analyze:

The execute and analyze pattern
===============================

The "execute and analyze" pattern generates a collection of :ref:`test cases <basics-testcase>` consisting of

* a :ref:`test file's <basics-testfile>` parameterized instantiations; and
* the test file's base, un-parameterized, case.

The base case runs only after all of the parameterized test cases are finished.

The execute and analyze pattern is enabled by adding :func:`nvtest.directives.generate_composite_base_case` to the test file's directives.

.. admonition:: vvtest compatibility

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

To take advantage of the execute and analyze pattern, a test should define separate functions for the parameterized and base test cases. For example, a test might define separate ``run_parameterized_case`` and ``analyze_base_case`` functions as below:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 9-22
    :language: python

The function ``run_parameterized_test`` is intended to be called for each parameterized child test  and the function ``analyze_composite_base_case`` the final composite base case (in which the children tests are made available in the ``nvtest.TestMultiInstance.dependencies`` attribute).

You can key off of the test instance type to determine which function to call:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 23-32
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
    :lines: 35-42
    :language: python

The ordering of the parameters is guaranteed to be the same as the ordering the ``dependencies``.  E.g., ``self.dependencies[i].parameters.a == self.parameters.a[i]``.

Additionally, a full table of dependency parameters is accessible via key entry into the ``parameters`` attribute, where the key is a tuple containing each individual parameter name, e.g.:

.. literalinclude:: /examples/analyze_only/analyze_only.pyt
    :lines: 32-39
    :language: python

Run only the analysis section of a test
---------------------------------------

After a test is run, the composite base case can be run with the :ref:`nvtest analyze<nvtest-analyze>` command.  Consider the test introduced in :ref:`usage-execute-and-analyze`, repeated here for convenience:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :language: python

After the test has been run, the analysis sections can be run without rerunning the (potentially expensive) test portion:

.. command-output:: nvtest run -d TestResults.ExecuteAndAnalyze ./execute_and_analyze
    :cwd: /examples
    :extraargs: -rv -w
    :ellipsis: 0


.. command-output:: nvtest -C TestResults.ExecuteAndAnalyze analyze .
    :cwd: /examples


Connection to additional execution stages
-----------------------------------------

The execute and analyze pattern is related to :ref:`usage-staged-execution` by adding the ``analyze`` stage to the composite base case's ``stages`` and adding each parameterized test case as a dependency.
