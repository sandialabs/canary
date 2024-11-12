.. _usage-rcfiles:

Source rc scripts during test execution
=======================================

Some tests require a modified environment.  When the required environment modifications are contained in rc files, ``nvtest`` can source the files prior to test execution.  There are two ways to modify the environment by sourcing an rc file:

1. Through the ``nvtest.shell.source`` context manager:

   .. code-block:: python

      import nvtest

      def test():
          with nvtest.shell.source("filename"):
              # do work

2. Through the ``nvtest.directives.source`` directive:

   .. code-block:: python

      import nvtest
      nvtest.directives.source("filename", when=...)

      def test():
          # do work

.. note::

  Only ``sh`` compatible rc files are supported.
