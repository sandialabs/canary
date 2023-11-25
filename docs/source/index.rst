.. nvtest documentation master file, created by
   sphinx-quickstart on Wed Oct 18 08:17:52 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

nvtest
======

``nvtest`` is an application testing framework designed to test scientific applications. ``nvtest`` is inspired by `vvtest <https://github.com/sandialabs/vvtest>`_ and designed to run tests on diverse hardware from laptops to super computing clusters.  ``nvtest`` not only validates the functionality of your application but can also serve as a workflow manager for analysts.  A "test" is an executable script with extension ``.pyt`` or ``.vvt`` [#]_.  If the exit code upon executing the script is ``0``, the test is considered to have passed, otherwise the test failed [#]_.  ``nvtest``'s methodology is simple: given a path on the filesystem, it recursively searches for test scripts, sets up the tests described in each script, executes them, and reports the results.

.. raw:: html

   <font size="+3"> Contents:</font>

.. toctree::
   :maxdepth: 2

   getting_started
   config
   session
   writing_tests
   howto/index
   reference/index
   subcommands/index
   directives/index


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. [#] ``.pyt`` scripts are written in python while ``.vvt`` scripts can be any executable recognized by the system, though scripts written in Python can take advantage of the full ``nvtest`` ecosystem.
.. [#] Other test outcomes are also possible, eg, ``diffed``, ``timeout``.  See :ref:`test-status`.
