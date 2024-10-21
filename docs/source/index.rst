.. nvtest documentation master file, created by
   sphinx-quickstart on Wed Oct 18 08:17:52 2023.

nvtest
======

``nvtest`` is an application testing framework designed to test scientific applications. ``nvtest`` is inspired by `vvtest <https://github.com/sandialabs/vvtest>`_ and designed to run tests on diverse hardware from laptops to super computing clusters.  ``nvtest`` not only validates the functionality of your application but can also serve as a workflow manager for analysts.  A "test" is an executable script with extension ``.pyt`` or ``.vvt`` [#]_.  If the exit code upon executing the script is ``0``, the test is considered to have passed, otherwise a non-passing :ref:`status <basics-status>` will be assigned.  ``nvtest``'s methodology is simple: given a path on the filesystem, ``nvtest`` recursively searches for test scripts, sets up the tests described in each script, executes them, and reports the results.

``nvtest`` offers several advantages over similar testing tools:

**Speed**: Hierarchical parallelism is used to run tests asynchronously, optimizing resource utilization and speeding up the testing process.  See :ref:`basics-resource` for more.

**Python**: Test files are written in `Python <python.org>`_, giving developers access to the full Python ecosystem.

**Integration**: ``nvtest`` :ref:`integrates<integrations>` with popular developer tools like :ref:`CMake <integrations-cmake>`, :ref:`CDash <integrations-cdash>`, and :ref:`GitLab <integrations-gitlab>`, streamlining the testing and continuous integration (CI) processes.

**Extensibility**: ``nvtest`` can be extended through :ref:`user plugins <extending>`, allowing developers to customize their test sessions according to their specific needs.

.. toctree::
   :maxdepth: 2

   introduction/index
   getting-started/index
   basics/index
   configuration/index
   extending/index
   integrations/index
   howto/index
   commands/index
   directives/index
   api-docs/index
   developers/index

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. [#] ``.pyt`` scripts are written in python while ``.vvt`` scripts can be any executable recognized by the system, though scripts written in Python can take advantage of the full ``nvtest`` ecosystem.
