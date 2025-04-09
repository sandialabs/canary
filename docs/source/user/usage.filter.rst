.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-filter:

Filtering tests
===============

``canary`` can perform filtering actions to reduce the number of tests run in a session.  Described next are the three main ways to filter tests via the command line: by :ref:`keyword expression <filter-kwd>`, by :ref:`parameter expression <filter-parameters>`, and by :ref:`platform expression <filter-platform>`.

.. _filter-kwd:

Filter by keyword
-----------------

Using ``-k`` on the command line, filters (selects) tests based on the :ref:`keywords<directive-keywords>` defined in each test. For example, consider two test files, ``parameterize1.pyt``:

.. code-block:: python

   import canary
   canary.directives.keywords("3D", "mhd", "circuit")
   print("running test1")

and ``parameterize2.pyt``:

.. code-block:: python

   import canary
   canary.directives.keywords("3D", "mhd", "conduction")
   print("running parameterize2")

Using the command ``canary run -k 3D`` would cause both tests to run, because they both have the keyword ``3D``. Using the command ``canary run -k circuit`` would run only ``parameterize2``, because only that test has the ``circuit`` keyword defined.

``-k`` can accept python expressions, eg, ``canary -k '3D and conduction'`` means run tests that satisfy the statement "3D is present in the keywords AND conduction is present".

Use ``not`` to do the inverse, eg, ``canary run -k 'not conduction'`` means run tests such that do not have the ``conduction`` keyword.

.. _filter-parameters:

Filter by parameters
--------------------

When tests define parameters using the :ref:`parameterize directive<directive-parameterize>`, then the resulting parameter names and values can be used to select tests.  Consider the test file ``p1.pyt``

.. code-block:: python

   import canary
   canary.directives.parameterize("cpus", (1, 4))
   print("running test p1")

and the test file ``p2.pyt``:

.. code-block:: python

   import canary
   canary.directives.parameterize("MODEL", ("elastic", "elasticplastic"))
   print("running test p2")

The command ``canary run -p cpus`` would only run test ``p1``, because the ``cpus`` parameter is only defined in that test file.  In general, specifying a parameter name means include the test if the parameter is defined by the test.

The value of a parameter can be specified as well. For example, the command ``canary run -p MODEL=elastic`` would only run the ``p2.MODEL=elastic`` test and no others. In general, ``-p name=value`` means run any test that defines the parameter ``name`` and which has the value ``value``.

More comparison operators in addition to ``=`` can be used, such as ``>``, ``<``, ``>=``, ``!=``, etc. For example, the command ``canary run -p 'cpus>1'`` would run the ``p1.cpus=4`` test and no others.

Implicit parameters
~~~~~~~~~~~~~~~~~~~

The following implicit parameters defined for filtering purposes:

* ``np``: alias to ``cpus``
* ``ndevice``: alias to ``gpus``
* ``runtime``: the test runtime in seconds
* ``timeout``: the test timeout in seconds

For example, tests having a running time exceeding 30 seconds can be filtered by

.. code-block:: console

   canary run -p 'runtime <= 30' ...


.. _filter-platform:

Filter by platform
------------------

A test can use the ``enable`` directive to limit the platforms that will run the test. For example, the test ``atest.vvt``

.. code-block:: python

   import canary
   canary.directives.enable(when="platforms='Darwin'")
   ...

will only run if the platform name is ``Darwin``. Expressions are allowed as the ``platform`` attribute value, such as ``when="platforms='Darwin or Linux'"``, or ``when="platforms='not Darwin'"``.
