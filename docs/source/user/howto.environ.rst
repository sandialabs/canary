.. _howto-environ:

Modify your environment with modules and rc files
=================================================

Some tests require a modified environment.  When the required environment modifications are contained in module and/or rc files use the following constructs.

Modify your environment by loading a module
-------------------------------------------

There are two ways to modify the environment by loading a module:

1. Through the ``nvtest.module.load`` context manager:

   .. code-block:: python

      import nvtest

      def test():
          with nvtest.module.load("modulename"):
            # do work

   To add the module's path to ``MODULEPATH``

   .. code-block:: python

      def test():
          with nvtest.module.load("modulename", use="modulepath"):
            # do work

2. Through the ``nvtest.directives.load_module`` directive:

   .. code-block:: python

      import nvtest
      nvtest.directives.load_module("modulename", use=..., when=...)

      def test():
          # do work


Modify the environment sourcing an rc file
------------------------------------------

There are two ways to modify the environment by sourcing an rc file:

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
