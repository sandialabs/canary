.. _howto-guides:

How-to guides
=============

The how-to guides in the documentation were auto-generated using a set of examples distributed with ``nvtest``'s source code.  To run the examples, clone the ``nvtest`` repository and navigate to ``tests/examples`` where all of the examples in the guide are run.

.. note::

   When the documentation is created, two flags are implicitly sent to ``nvtest run``:

   * ``-w``: removes the test execution directory before starting a new test session.
   * ``-rv``: Verbose test execution.

.. toctree::
   :maxdepth: 1

   finding
   basic
   run_from_file
   batch
   parameterize
   execute_and_analyze
   analyze_only
   copy_and_link
   enable
   status
   filter
   log
   location
   xstatus
   centered_parameter_space
   cmake
   ctest
   report
   plugins
