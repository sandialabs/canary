:html_theme.sidebar_secondary.remove: true

.. template taken from Pandas

nvtest
======

.. toctree::
   :maxdepth: 1
   :hidden:

   User's guide <user/index>
   API reference <api-docs/index>
   Developer's guide <dev/index>
   Release notes<release/index>
   Tutorial<tutorial/index>
   Presentation<presentation/index>

``nvtest`` is an application testing framework designed to test scientific applications. ``nvtest`` is inspired by `vvtest <https://github.com/sandialabs/vvtest>`_ and designed to run tests on diverse hardware from laptops to super computing clusters.  ``nvtest`` not only validates the functionality of your application but can also serve as a workflow manager for analysts.  A "test" is an executable script with extension ``.pyt`` or ``.vvt`` [#]_.  If the exit code upon executing the script is ``0``, the test is considered to have passed, otherwise a non-passing :ref:`status <basics-status>` will be assigned.  ``nvtest``'s methodology is simple: given a path on the filesystem, ``nvtest`` recursively searches for test scripts, sets up the tests described in each script, executes them, and reports the results.

``nvtest`` offers several advantages over similar testing tools:

**Speed**: Hierarchical parallelism is used to run tests asynchronously, optimizing resource utilization and speeding up the testing process.  See :ref:`basics-resource` for more.

**Python**: Test files are written in `Python <python.org>`_, giving developers access to the full Python ecosystem.

**Integration**: ``nvtest`` :ref:`integrates<integrations>` with popular developer tools like :ref:`CMake <integrations-cmake>`, :ref:`CDash <integrations-cdash>`, :ref:`CTest <integrations-ctest>`, and :ref:`GitLab <integrations-gitlab>`, streamlining the testing and continuous integration (CI) processes.

**Extensibility**: ``nvtest`` can be extended through :ref:`user plugins <extending>`, allowing developers to customize their test sessions according to their specific needs.

.. grid:: 1 1 2 2
   :gutter: 2 3 4 4

   .. grid-item-card::
      :text-align: center

      :octicon:`paper-airplane;2em`

      .. button-ref:: user/getting-started
         :expand:
         :color: primary
         :click-parent:

         Getting started

   .. grid-item-card::
      :text-align: center

      :octicon:`book;2em`

      .. button-ref:: user/index
         :expand:
         :color: primary
         :click-parent:

         User's guide

   .. grid-item-card::
      :text-align: center

      :octicon:`file-code;2em`

      .. button-ref:: api-docs/index
         :expand:
         :color: primary
         :click-parent:

         API reference

   .. grid-item-card::
      :text-align: center

      :octicon:`code;2em`

      .. button-ref:: dev/index
         :expand:
         :color: primary
         :click-parent:

         Developer's guide

.. [#] ``.pyt`` scripts are written in python while ``.vvt`` scripts can be any executable recognized by the system, though scripts written in Python can take advantage of the full ``nvtest`` ecosystem.
