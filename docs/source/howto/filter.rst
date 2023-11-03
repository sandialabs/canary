How to filter and select tests
==============================

The tests that are selected to run in a given ``nvtest`` invocation is called "filtering the tests", which is important when managing a large set of tests. Described next are the three main ways to filter tests via the command line: by :ref:`keyword expression <directive-keywords>`, by :ref:`parameter expression <directive-parameters>`, and by `platform expression <directive-platform>`.

Filter by keyword
-----------------

Using ``-k`` on the command line, filters (selects) tests based on the keywords defined in each test. For example, consider two test files, ``test1.pyt``:

.. code-block:: python

   import nvtest
   nvtest.mark.keywords("3D", "mhd", "circuit")
   print("running test1")

and ``test2.pyt``:

.. code-block:: python

   import nvtest
   nvtest.mark.keywords("3D", "mhd", "conduction")
   print("running test2")

Using the command ``nvtest run -k 3D`` would cause both tests to run, because they both have the keyword ``3D``. Using the command ``nvtest run -k circuit`` would run only ``test2``, because only that test has the ``circuit`` keyword defined.

``-k`` can accept python expressions, eg, ``nvtest -k '3D and conduction'`` means run tests that satisfy the statement "3D is present in the keywords AND conduction is present".

Use ``not`` to do the inverse, eg, ``nvtest run -k 'not conduction'`` means run tests such that do not have the ``conduction`` keyword.

Filtering by parameters
-----------------------

When tests define parameters using the ``parameterize`` directive, then the resulting parameter names and values can be used to select tests.  Consider the test file ``p1.pyt``

.. code-block:: python

   import nvtest
   nvtest.mark.parameterize("np", (1, 4))
   print("running test p1")

and the test file ``p2.vvt``:

.. code-block:: python

   import nvtest
   nvtest.mark.parameterize("MODEL", ("elastic", "elasticplastic"))
   print("running test p2")

The command ``nvtest run -p np`` would only run test ``p1``, because the ``np`` parameter is only defined in that test file.  In general, specifying a parameter name means include the test if the parameter is defined by the test.

The value of a parameter can be specified as well. For example, the command ``nvtest run -p MODEL=elastic`` would only run the ``p2.MODEL=elastic`` test and no others. In general, ``-p name=value`` means run any test that defines the parameter ``name`` and which has the value ``value``.

More comparison operators in addition to ``=`` can be used, such as ``>``, ``<``, ``>=``, ``!=``, etc. For example, the command ``nvtest run -p 'np>1'`` would run the ``p1.np=4`` test and no others.

Filter by platform
------------------

A test can use the ``enable`` directive to limit the platforms that will run the test. For example, the test ``atest.vvt``

.. code-block:: python

   import nvtest
   nvtest.mark.enable(platforms="Darwin")
   ...

will only run if the platform name is ``Darwin``. Expressions are allowed as the ``platform`` attribute value, such as ``platforms="Darwin or Linux"``, or ``platforms="not Darwin"``.
