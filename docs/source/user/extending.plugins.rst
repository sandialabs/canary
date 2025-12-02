.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-plugins:

Extend canary with plugins
==========================

The default behavior of ``canary`` can be modified with user defined plugins.  A plugin is a python function that is called at different phases of the ``canary`` workflow.  Plugins are loaded and managed by `pluggy <https://pluggy.readthedocs.io/en/stable/>`_.

Plugin discovery
----------------

``canary`` loads plugin modules in the following order:

* Builtin plugins.
* Plugins specified by the ``CANARY_PLUGINS=plugin_1,...,plugin_n`` environment variable.
* Plugins registered through `setuptools entry points <https://docs.pytest.org/en/7.1.x/how-to/writing_plugins.html#setuptools-entry-points>`_ ``canary`` looks up the ``canary`` entrypoint to discover its plugins.  Make your plugin available by defining it in your ``pyproject.toml``:

  .. code-block:: toml

     [project.entry-points.canary]
     plugin_name = "myproject.pluginmodule"
* Plugins specified in the ``plugins`` configuration field.
* Local plugins specified by the ``-p NAME`` command line option.  ``NAME`` is the name of the python module containing the plugins and must be importable.

Writing plugins
---------------

Plugin functions are registered with ``canary`` by decorating with ``canary.hookimpl`` decorator:

.. code-block:: python

    @canary.hookimpl
    def canary_plugin_name(...):
       ...

Recognized plugin hooks defined in :ref:`hookspec`.

Examples
--------

* Mask a test from running that appears in an exclude list:

  .. code-block:: python

    import canary

    @canary.hookimpl
    def canary_select_modifyitems(selector: canary.Selector):
        for spec in selector.specs:
            if spec.name in EXCLUSION_DB:
                spec.mask = canary.Mask.masked("excluded due to ...")


* Add a flag to turn on test coverage and set the ``LLVM_PROFILE_FILE`` environment variable:

  .. code-block:: python

    import canary

    @canary.hookimpl
    def canary_addoption(parser: canary.Parser) -> None:
        parser.add_plugin_argument(
            "--code-coverage",
            action="store_true",
            default=False,
            help="Create and export coverage data",
        )

    @canary.hookimpl
    def canary_select_modifyitems(selector: canary.Selector) -> None:
        if not canary.config.getoption("code_coverage"):
            return
        if spec.mask:
            return
        spec.environment["LLVM_PROFILE_FILE"] = f"{case.name}.profraw"

    @canary.hookimpl
    def canary_sessionfinish(session: canary.Session) -> None:
        if not canary.config.getoption("code_coverage"):
            return
        files = find_raw_profiling_files(session.root)
        combined_files = combine_profiling_files(files)
        create_coverage_maps(combined_files)
