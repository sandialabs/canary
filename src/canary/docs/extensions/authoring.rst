.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _authoring-extensions:

Authoring extensions
====================

A ``canary`` extension is a Python package that hooks into the canary
lifecycle via `pluggy <https://pluggy.readthedocs.io/>`_.  This page covers
everything needed to build, test, document, and distribute one.


Plugin discovery
----------------

``canary`` loads plugins in priority order:

1. Built-in plugins (collection, generation, execution, resource pool, …)
2. Packages registered under the ``canary`` `entry point group`_
3. ``CANARY_PLUGINS=name1,name2`` environment variable
4. ``plugins`` field in the configuration file
5. ``-p NAME`` command-line option (module must be importable)

Later sources override earlier ones.

.. _entry point group: https://packaging.python.org/en/latest/specifications/entry-points/


Registering via entry points
-----------------------------

Declare the entry point in ``pyproject.toml``:

.. code-block:: toml

   [project.entry-points."canary"]
   my_plugin = "my_package.plugin_module"

canary discovers every package registered in the ``canary`` group
automatically when it is installed, so no manual loading step is required.

To disable a specific plugin at runtime:

.. code-block:: console

   CANARY_PLUGINS=no:builtin.gpu_select canary run .


Writing hooks
-------------

Decorate module-level functions with ``@canary.hookimpl``:

.. code-block:: python

   import canary

   @canary.hookimpl
   def canary_addoption(parser: canary.Parser) -> None:
       parser.add_argument(
           "--my-flag",
           action="store_true",
           group="my plugin",
           command="run",
           help="Enable my custom behaviour.",
       )

   @canary.hookimpl
   def canary_configure(config: canary.Config) -> None:
       if config.getoption("my_flag"):
           ...

See :ref:`extending` for the full set of available hooks and worked examples.


Package layout
--------------

A minimal extension package looks like this:

.. code-block:: text

   my_plugin/
   ├── pyproject.toml
   ├── src/
   │   └── my_plugin/
   │       ├── __init__.py          ← hookimpl functions here
   │       ├── data/
   │       │   ├── __init__.py
   │       │   ├── capabilities.json
   │       │   └── skills.json
   │       ├── docs/
   │       │   ├── .canary-ext-docs ← marker — tells canary this folder contains docs
   │       │   ├── index.rst
   │       │   └── ...
   │       └── tests/
   │           └── test_my_plugin.py
   └── tests/                       ← OR tests at project root
       └── test_my_plugin.py


Capabilities and skills
-----------------------

Implement ``canary_capabilities()`` and ``canary_skills()`` to make your plugin
queryable via ``canary query -c`` and ``canary learn``:

.. code-block:: python

   from typing import Any

   @canary.hookimpl
   def canary_capabilities() -> dict[str, Any] | None:
       from _canary.util.query_data import load_query_data
       return load_query_data("my_plugin.data", "capabilities.json")

   @canary.hookimpl
   def canary_skills() -> dict[str, Any] | None:
       from _canary.util.query_data import load_query_data
       return load_query_data("my_plugin.data", "skills.json")

Both files must follow the ``schema_version: "2.0.0"`` format.  See
``src/canary_pyt/data/capabilities.json`` for a complete example.


Tests
-----

Place tests in a ``tests/`` directory inside your source tree (or at the
project root — either is fine).  canary's pre-commit hook runs the test
suites of all installed extensions:  every ``canary run`` on the main canary
repository automatically runs ``pytest`` for each plugin that shipped tests.

To be picked up, tests must be standard ``pytest`` test files (``test_*.py``
or ``*_test.py``).  A minimal test for the plugin registration itself:

.. code-block:: python

   def test_capabilities_hook():
       from my_plugin import canary_capabilities
       result = canary_capabilities()
       assert result is not None
       assert result["namespace"] == "my_plugin"

Run your tests locally with:

.. code-block:: console

   pytest tests/


Documentation
-------------

Extensions that ship documentation will have it automatically included in
the built canary docs.

**Steps:**

1. Create a ``docs/`` folder inside your package source directory
   (e.g. ``src/my_plugin/docs/``).

2. Add an empty marker file:

   .. code-block:: console

      touch src/my_plugin/docs/.canary-ext-docs

3. Add an ``index.rst`` as the entry point — this is the page that will be
   linked from the main extensions index.

4. Add ``docs/**`` to ``[tool.setuptools.package-data]`` in ``pyproject.toml``
   so the RST files are included in the installed wheel:

   .. code-block:: toml

      [tool.setuptools.package-data]
      my_plugin = ["docs/**", "data/*.json"]

**How discovery works:**

At documentation build time, ``conf.py`` scans every installed ``canary``
entry point.  For each one it locates the installed package using
``importlib.resources``, checks for ``docs/.canary-ext-docs``, and if found
copies the ``docs/`` tree into ``extensions/exts/<entry-point-name>/`` so
Sphinx can include it.  The ``extensions/index.rst`` toctree uses a glob
(``exts/*/index``) to pick them all up automatically.

This means:

- External plugins (e.g. ``canary-notebook``) get their docs included
  automatically if they ship a ``docs/.canary-ext-docs`` marker.
- No manual editing of any canary index file is required.
- The ``extensions/exts/`` directory is git-ignored in the canary repo;
  only the authored ``extensions/index.rst`` and ``extensions/authoring.rst``
  are tracked.
