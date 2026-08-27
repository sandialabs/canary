.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

:html_theme.sidebar_secondary.remove: true

.. template taken from Pandas

canary
======

.. toctree::
   :maxdepth: 1
   :hidden:

   User's guide <user/index>
   API reference <api/index>
   Command Reference <reference/index>
   Extensions <extensions/index>
   Examples <examples/index>
   Tutorial <tutorial/index>
   Extending Canary <extending/index>
   Changelog <changelogs/index>

``canary`` is an application testing framework designed to test scientific applications. ``canary`` is inspired by `vvtest <https://github.com/sandialabs/vvtest>`_ and designed to run tests on diverse hardware from laptops to super computing clusters.  ``canary`` not only validates the functionality of your application but can also serve as a workflow manager for analysts.  A "test" is an executable script with extension ``.pyt`` or ``.vvt`` [#]_.  If the exit code upon executing the script is ``0``, the test is considered to have passed, otherwise a non-passing status will be assigned.  ``canary``'s methodology is simple: given a path on the filesystem, ``canary`` recursively searches for test scripts, sets up the tests described in each script, executes them, and reports the results.

``canary`` offers several advantages over similar testing tools:

**Speed**: Hierarchical parallelism is used to run tests asynchronously, optimizing resource utilization and speeding up the testing process.

**Python**: Test files are written in `Python <https://www.python.org>`_, giving developers access to the full Python ecosystem.

**Integration**: ``canary`` integrates with popular developer tools like CMake, CDash, CTest, and GitLab, streamlining the testing and continuous integration (CI) processes.

**Extensibility**: ``canary`` can be extended through user plugins, allowing developers to customize their test sessions according to their specific needs.

.. [#] ``.pyt`` scripts are written in python while ``.vvt`` scripts can be any executable recognized by the system, though scripts written in Python can take advantage of the full ``canary`` ecosystem.