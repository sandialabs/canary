.. _howto-execute-and-analyze:

How to write an execute and analyze test
========================================

An execute/analyze test is one that uses parameters to expand into multiple test instances, followed by a final test instance that analyzes the results.  The analyze test only runs after all the parameter tests are finished.

The addition of the ``nvtest.directives.analyze`` directive marks a test as an execute/analyze test and will create a separate test for performing the analysis.

Consider the following test file ``test.pyt``

.. literalinclude:: /examples/execute_and_analyze/test.pyt
    :language: python
    :lines: 1-6

and associated dependency graph

.. program-output:: nvtest describe test.pyt
    :cwd: /examples/execute_and_analyze

When this test is run, ``test[a=1]``, ``test[a=2]``, and ``test[a=3]`` are run first and then ``test``.  This last test is the analyze test.  The "children" tests are made available to ``test`` in the ``nvtest.test.instance.dependencies`` attribute as shown in the ``analyze`` function of the full example:

.. literalinclude:: /examples/execute_and_analyze/test.pyt
    :language: python
