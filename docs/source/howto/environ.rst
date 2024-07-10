.. _howto-environ:

Modify your environment with modules and rc files
=================================================

Some tests require a modified environment.  When the required environment modifications are contained in module and/or rc files use the following constructs.

* To modify your environment by loading a module:

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

* To modify your environment by sourcing an rc file

  .. code-block:: python

     import nvtest

     def test():
         with nvtest.shell.source("filename"):
             # do work

  .. note::

    Only ``sh`` compatible rc files are supported.
