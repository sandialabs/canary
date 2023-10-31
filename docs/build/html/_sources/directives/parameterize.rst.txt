.. _directive-parameterize:

parameterize
============

Add new invocations to the test using the list of argvalues for the given argnames.

.. code-block:: python

   parametrize(argnames, argvalues, options=None, platforms=None, testname=None)


.. code-block:: python

   #VVT: parametrize (options=...,platforms=...,testname=...) : argnames = argvalues

Parameters
----------

* ``argnames``: A comma-separated string denoting one or more argument names, or a list/tuple of argument strings.
* ``argvalues``: The list of ``argvalues`` determines how often a test is invoked with different argument values.  If only one ``argname`` was specified, ``argvalues`` is a list of values. If ``N`` ``argnames`` were specified, ``argvalues`` must be a list of N-tuples, where each tuple-element specifies a value for its respective ``argname``.
* ``testname``: Restrict processing of the directive to this test name
* ``platform``: Restrict processing of the directive to certain platform or platforms
* ``option``: Restrict processing of the directive to command line ``-o`` options

Special argnames
----------------

The ``np`` parameter is interpreted to mean "number of processing cores".  If the ``np`` parameter is not defined, the test is assumed to use 1 processing core.

References
----------

* :ref:`Parameterizing Tests <parameterizing>`

Examples
--------

The following equivalent test specifications result in 4 test instantiations

``test1.pyt``:

.. code-block:: python

   # test1
   nvtest.mark.parameterize("np", (4, 8, 12, 32))

``test1.vvt``:

.. code-block:: python

   # test1
   #VVT: parameterize : np = 4 8 12 32

.. code-block:: console

   4 test cases:
   ├── test1[np=4]
   ├── test1[np=8]
   ├── test1[np=12]
   ├── test1[np=32]

----

``argnames`` can be a list of parameters with associated ``argvalues``, e.g.

``test1.pyt``:

.. code-block:: python

   # test1
   nvtest.mark.parameterize("a,b", ((1, 2), (3, 4), (5, 6)])

``test1.vvt``:

.. code-block:: python

   # test1
   #VVT: parameterize : a,b = 1,2 3,4 5,6

.. code-block:: console

   4 test cases:
   ├── test1[a=1,b=2]
   ├── test1[a=3,b=4]
   ├── test1[a=5,b=6]

----

``parameterize`` can be called multiple times.  When multiple parameterize directives are given, the Cartesian product of each is taken to form the set of parameters, e.g.

``test1.pyt``:

.. code-block:: python

   # test1
   nvtest.mark.parameterize("a,b", [("a1", "b1"), ("a2", "b2")])
   nvtest.mark.parameterize("x", ["x1", "x2"])

results in the following test invocations:

.. code-block:: console

   4 test cases:
   ├── test1[a=a1,b=b1,x=x1]
   ├── test1[a=a1,b=b1,x=x2]
   ├── test1[a=a2,b=b2,x=x1]
   ├── test1[a=a2,b=b2,x=x2]
