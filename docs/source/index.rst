.. nvtest documentation master file, created by
   sphinx-quickstart on Wed Oct 18 08:17:52 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

nvtest
======

``nvtest`` is a testing framework designed to test scientific applications. ``nvtest`` is inspired by `vvtest <https://github.com/sandialabs/vvtest>`_ and designed to run tests on diverse hardware from laptops to super computing clusters.

``nvtest``'s methodology is simple: given a path, it recursively searches for test files ending in ``.pyt`` or ``.vvt`` and executes them.  If the exit code from a executing a test file is ``0`` the test is considered passing, otherwise it failed.

.. raw:: html

   <font size="+3"> Contents:</font>

.. toctree::
   :maxdepth: 2

   getting_started
   installing
   howto/index
   reference/index
   subcommands/index
   directives/index


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
