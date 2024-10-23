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

Consider the following test file ``examples/execute_and_analyze/execute_and_analyze.pyt``

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :language: python
    :lines: 1-6

The dependency graph for this test is

.. command-output:: nvtest describe execute_and_analyze/execute_and_analyze.pyt
    :cwd: /examples

As can be seen, the base case ``execute_and_analyze`` depends on ``execute_and_analyze[a=1]``, ``execute_and_analyze[a=2]``, and ``execute_and_analyze[a=3]``.  When the test is run, these "children" tests are run first and then the base case:

.. command-output:: nvtest run -d TestResults.ExecuteAndAnalyze ./execute_and_analyze
    :cwd: /examples
    :extraargs: -rv -w

The full example
----------------

Define separate functions for the "test" and "analyze" portions of the test, as defined in the ``test`` and ``analyze_parameterized_test`` functions below.

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 9-22
    :language: python

``analyze_parameterized_test`` is intended to be called for each child test.

In the final base case, the children tests are made available in the ``nvtest.test.instance.dependencies`` attribute as shown in the ``analyze_base_case`` function below:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 24-30
    :language: python

Finally, the ``ExecuteAndAnalyze`` object is used to set up the test to broker which functions are called during different phases of the test:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :lines: 33-36
    :language: python

Accessing dependency parameters
-------------------------------

Dependency parameters can be accessed directly from the base test instance's ``dependencies``, eg,

.. code-block:: python

    self = nvtest.get_instance()
    self.dependencies[0].parameters

or, in the base test instance's ``parameters`` attribute.  Consider the following test:

.. literalinclude:: /examples/analyze_only/analyze_only.pyt
    :lines: 8-10
    :language: python

The parameters ``np``, ``a``, and ``b`` of each dependency can be accessed directly:

.. literalinclude:: /examples/analyze_only/analyze_only.pyt
    :lines: 30-32
    :language: python

The ordering of the parameters is guaranteed to be the same as the ordering the ``dependencies``.  Eg, ``self.dependencies[i].parameters.a == self.parameters.a[i]``.

Additionally, a full table of dependency parameters is accessible via key entry into the ``parameters`` attribute, where the key is a tuple containing each individual parameter name, eg:

.. literalinclude:: /examples/analyze_only/analyze_only.pyt
    :lines: 33-40
    :language: python
