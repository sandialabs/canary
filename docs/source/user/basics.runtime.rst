.. _basics-runtimes:

Time resources
==============

Runtime
-------

Test runtimes are written to ``<root>/.nvtest_cache/timing``, where ``<root>`` is the root test search directory.  This cache is automatically created when a session is run and can be ignored from source control.  However, if the timing cache is kept and updated, the data contained therein can aid in speeding up :ref:`batched <howto-run-batched>` test runs by allowing more accurate determinations of batch sizes.

Timeout
-------

A test case's timeout can be set by the :ref:`timeout <directive-timeout>` directive.  For example, to set a tests timeout to 5 minutes add the following the test file:

.. code-block:: python

   import nvtest
   nvtest.directives.timeout(5 * 60)

If the timeout is not explicitly set, it is set based on the presence of the ``fast`` and ``long`` keywords in a manner similar to `vvtest <https://cee-gitlab.sandia.gov/scidev/vvtest>`_:

* If a test is marked ``fast``, its timeout defaults to 30 seconds.
* If a test is marked ``long``, its timeout defaults to 10 minutes.
* Otherwise the timeout is 5 minutes.

These values are configurable in the ``test:timeout`` :ref:`configuration setting <nvtest-config>`:

.. code-block:: ini

   [test:timeout]
   fast = 30s
   long = 10m
   default = 5m

which can also be set from the command line, eg:

.. code-block:: console

   nvtest -c test:timeout:fast:60s ...

A timeout ``T`` for all tests in a session can also be set on the command line:

.. code-block:: console

   nvtest run -l test:timeout=T

Timeout multiplier
------------------

You may also want to increase the timeout applied to tests.  Do so by specifying ``-l test:timeoutx`` option:

.. code-block:: console

   nvtest run -l test:timeoutx=X ...

In this case, the timeout for each test will be the ``X`` times the test's default timeout.
