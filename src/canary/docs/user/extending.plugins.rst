.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-plugins:

Extend canary with plugins
==========================

The default behavior of ``canary`` can be modified with user-defined plugins.
A plugin is a Python module that implements one or more hook functions called at
specific phases of the ``canary`` workflow.  Plugins are loaded and managed by
`pluggy <https://pluggy.readthedocs.io/en/stable/>`_.

This page covers plugin discovery, registration, and basic authoring
patterns.  For small, local hook modules loaded with ``-p`` and used to attach
measurements or metadata, see :doc:`/user/usage.plugins`.

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
* Local plugins specified by the ``-p NAME`` command line option.  ``NAME`` may
  be an importable module name, a ``.py`` file, or a package directory.

Writing plugins
---------------

Plugin functions are registered with the ``canary.hookimpl`` decorator:

.. code-block:: python

    import canary

    @canary.hookimpl
    def canary_plugin_name(...):
        ...

Recognized hooks are documented in :doc:`/extensions/hooks`.

Minimal example
---------------

The following plugin records per-job metadata and then adds a session-level
count when the run completes:

.. code-block:: python

    import socket

    import canary


    @canary.hookimpl
    def canary_runteststart(case: canary.Job) -> None:
        case.add_measurement("hostname", socket.gethostname())


    @canary.hookimpl
    def canary_sessionfinish(session: canary.Session) -> None:
        n = 0
        for job in session.jobs:
            if "hostname" in job.measurements.data:
                n += 1
        session.add_measurement("jobs_with_hostname", n)

For many sites this is enough.  Larger plugins can add options, configuration
sections, commands, generators, or reporters.

Choosing hooks
--------------

Most developer-authored plugins begin with one of these hooks:

``canary_runteststart``
  Per-job setup after the workspace exists and before the job command runs.

``canary_runtest_finish``
  Per-job post-processing after the job command finishes.

``canary_sessionfinish``
  Session-level aggregation once the run is complete.

``canary_select_modifyitems``
  Selection-time masking or filtering of jobs before execution.

For the complete lifecycle and ordering rules, see :doc:`/extensions/hooks`.

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


* Add a flag to turn on test coverage and set the ``LLVM_PROFILE_FILE``
  environment variable:

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
          for spec in selector.specs:
              if spec.mask:
                  continue
              spec.environment["LLVM_PROFILE_FILE"] = f"{spec.name}.profraw"

      @canary.hookimpl
      def canary_sessionfinish(session: canary.Session) -> None:
          if not canary.config.getoption("code_coverage"):
              return
          files = find_raw_profiling_files(session.prefix)
          combined_files = combine_profiling_files(files)
          create_coverage_maps(combined_files)
