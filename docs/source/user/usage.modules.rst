.. _usage-modules:

Loading modules in your test environment
========================================

Some tests require a modified environment.  When the required environment modifications are contained in module, ``canary`` can load the module prior to test execution.  There are two ways to modify the environment by loading a module:

1. Through the ``canary.module.load`` context manager:

   .. code-block:: python

      import canary

      def test():
          with canary.module.load("modulename"):
            # do work

   To add the module's path to ``MODULEPATH``

   .. code-block:: python

      def test():
          with canary.module.load("modulename", use="modulepath"):
            # do work

2. Through the :func:`canary.directives.load_module` directive:

   .. code-block:: python

      import canary
      canary.directives.load_module("modulename", use=..., when=...)

      def test():
          # do work
