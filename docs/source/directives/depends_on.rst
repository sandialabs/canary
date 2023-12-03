.. _directive-depends-on:

depends_on
==========

Specify a test dependency.  The test will run only after all dependencies have run.

.. code-block:: python

   depends_on(arg, parameters=None, testname=None, expect=None, result=None)

.. code-block:: python

   # VVT: depends on (parameters=..., testname=..., expect=..., result=...) : arg

Parameters
----------

* ``arg``: Dependency spec.  Can be a test name or glob expression
* ``parameters``: Restrict processing of the directive to certain parameter names and values
* ``testname``: Restrict processing of the directive to this test name
* ``expect``: Number of dependencies to expect to be found (in case that ``arg`` is a regular expression)
* ``result``: Run only if the dependency's result matches ``result``.  By default, a test will run if its dependency's result is ``pass`` or ``diff``.  Expressions are allowed, eg, ``not fail``.  The wildcard ``*`` means run the dependent test unconditionally.
