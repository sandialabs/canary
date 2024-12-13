.. _tutorial-dependencies-base:

Generating the base case
========================

A single test file can generate multiple parameter-specific test cases. Optionally, a non-parameterized "base" case can be generated that depends on each of the parameterized cases by calling :func:`nvtest.directives.generate_composite_base_case`:

.. literalinclude:: /examples/execute_and_analyze/execute_and_analyze.pyt
    :language: python

In this example, the base case that depends on test cases having ``a=1``, ``a=2``, and ``a=3``, is automatically generated:

.. command-output:: nvtest describe execute_and_analyze/execute_and_analyze.pyt
    :cwd: /examples

The base will not run until each parameterized case is run.
