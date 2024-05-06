.. nvtest documentation master file, created by
   sphinx-quickstart on Wed Oct 18 08:17:52 2023.

nvtest
======

``nvtest`` is an application testing framework designed to test scientific applications. ``nvtest`` is inspired by `vvtest <https://github.com/sandialabs/vvtest>`_ and designed to run tests on diverse hardware from laptops to super computing clusters.  ``nvtest`` not only validates the functionality of your application but can also serve as a workflow manager for analysts.  A "test" is an executable script with extension ``.pyt`` or ``.vvt`` [#]_.  If the exit code upon executing the script is ``0``, the test is considered to have passed, otherwise a non-passing :ref:`status <test-status>` will be assigned.  ``nvtest``'s methodology is simple: given a path on the filesystem, it recursively searches for test scripts, sets up the tests described in each script, executes them, and reports the results.

``nvtest`` offers several advantages over similar testing tools:

**Speed**: Hierarchical parallelism is used to run tests asynchronously, optimizing resource utilization and speeding up the testing process.  See :ref:`nvtest-resource` for more.

**Python**: Test files are written in `Python <python.org>`_, giving developers access to the full Python ecosystem.

**Integration**: ``nvtest`` integrates with popular developer tools like :ref:`CMake <howto-cmake-integration>`, :ref:`CDash <howto-cdash>`, and :ref:`GitLab <howto-gitlab>`, streamlining the testing and continuous integration (CI) processes.

**Extensibility**: ``nvtest`` can be extended through :ref:`user plugins <howto-plugins>`, allowing developers to customize their test sessions according to their specific needs.

.. toctree::
   :maxdepth: 1

   introduction/index
   basics/index
   tutorial
   howto/index
   directives/index
   commands/index

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. [#] ``.pyt`` scripts are written in python while ``.vvt`` scripts can be any executable recognized by the system, though scripts written in Python can take advantage of the full ``nvtest`` ecosystem.
