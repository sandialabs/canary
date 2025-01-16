.. _usage-rcfiles:

Sourcing rc scripts during test execution
=========================================

Some tests require a modified environment.  When the required environment modifications are contained in rc files, ``canary`` can source the files prior to test execution.  There are two ways to modify the environment by sourcing an rc file:

1. Through the ``canary.shell.source`` context manager:

   .. code-block:: python

      import canary

      def test():
          with canary.shell.source("filename"):
              # do work

2. Through the :func:`canary.directives.source` directive:

   .. code-block:: python

      import canary
      canary.directives.source("filename", when=...)

      def test():
          # do work

.. note::

  Only ``sh`` compatible rc files are supported.
