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

   howto.finding
   howto.basic
   howto.rerun
   howto.run_from_file
   howto.batch
   howto.parameterize
   howto.analyze_only
   howto.copy_and_link
   howto.enable
   howto.status
   howto.filter
   howto.log
   howto.location
   howto.xstatus
   howto.centered_parameter_space
   howto.environ
   howto.report
   howto.plugins
