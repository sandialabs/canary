.. _nvtest-runtimes:

Runtimes
========

Test runtimes are written to ``<root>/.nvtest_cache/timing``.  This cache is automatically created when a session is run and can be ignored from source control.  However, if the timing cache is kept and updated, the data contained therein can aid in speeding up :ref:`batched <howto-run-batched>` test runs by allowing more accutate determinations of batch sizes.
