.. _nvtest-runtimes:

Time resources
==============

Runtime
-------

Test runtimes are written to ``<root>/.nvtest_cache/timing``, where ``<root>`` is the root test search directory.  This cache is automatically created when a session is run and can be ignored from source control.  However, if the timing cache is kept and updated, the data contained therein can aid in speeding up :ref:`batched <howto-run-batched>` test runs by allowing more accurate determinations of batch sizes.

Timeout
-------

A test case's timeout can be set by the :ref:`timeout <directive-timeout>` directive.  If the timeout is not explicitly set, it is set based on the presence of the ``fast`` and ``long`` keywords in a manner similar to `nvtest <https://cee-gitlab.sandia.gov/scidev/vvtest>`_:

* If a test is marked ``fast``, its timeout defaults to 30 seconds.
* If a test is marked ``long``, its timeout defaults to 10 minutes.
* Otherwise the timeout is 5 minutes.

These values are configurable in the ``test:timeout`` :ref:`configuration setting <config-settings>`:

.. code-block:: ini

   [test:timeout]
   fast = 30 sec
   long = 10 min
   default = 5 min
