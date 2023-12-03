.. _directive-processors:

processors
==========

Run the test with this many processors

.. code-block:: python

   processors(*nprocs, options=None, platforms=None, testname=None)


.. code-block:: python

   #VVT: parametrize (options=...,platforms=...,testname=...) : np = nprocs

Parameters
----------

* ``nprocs``: List of processor counts
* ``testname``: Restrict processing of the directive to this test name
* ``platform``: Restrict processing of the directive to certain platform or platforms
* ``option``: Restrict processing of the directive to command line ``-o`` options

Examples
--------

The following equivalent test specifications result in 4 test instantiations

``test1.pyt``:

.. code-block:: python

   # test1
   nvtest.directives.processors(4, 8, 12, 32)

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
   nvtest.directives.parameterize("a,b", ((1, 2), (3, 4), (5, 6)])

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
   nvtest.directives.parameterize("a,b", [("a1", "b1"), ("a2", "b2")])
   nvtest.directives.parameterize("x", ["x1", "x2"])

results in the following test invocations:

.. code-block:: console

   4 test cases:
   ├── test1[a=a1,b=b1,x=x1]
   ├── test1[a=a1,b=b1,x=x2]
   ├── test1[a=a2,b=b2,x=x1]
   ├── test1[a=a2,b=b2,x=x2]
