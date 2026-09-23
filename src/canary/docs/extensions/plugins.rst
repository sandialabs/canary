.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-plugins:

Plugins
=======

Canary's plugin system extends functionality through a comprehensive hook architecture. Plugins integrate seamlessly with Canary's lifecycle, providing custom behavior while maintaining compatibility.

Plugin Discovery Order
----------------------

Canary loads plugins in this order:

1. **Built-in plugins**: Core Canary functionality

   - **builtin.collect**: Test collection and discovery
   - **builtin.generate**: Job generation from test files
   - **builtin.hooks**: Core hook implementations
   - **builtin.launcher**: Job execution launchers
   - **builtin.select**: Job selection and filtering
   - **builtin.resource_pool**: Resource management
   - **builtin.gpu_select**: GPU resource handling

2. **Setuptools entry points**: Plugins registered via ``canary`` entry point

3. **Environment variable**: ``CANARY_PLUGINS=plugin1,plugin2``

4. **Configuration file**: ``plugins`` field in configuration

5. **Command line**: ``-p NAME`` for local plugin modules

Later sources override earlier ones, allowing progressive customization.

Entry Points
------------

Register plugins via setuptools entry points in ``pyproject.toml``:

.. code-block:: toml

   [project.entry-points.canary]
   my_plugin = "my_package.plugin_module"

Canary automatically discovers all plugins under the ``canary`` entry point group.

Environment Variable Configuration
-----------------------------------

Load plugins via ``CANARY_PLUGINS`` environment variable:

.. code-block:: console

   $ CANARY_PLUGINS=plugin1,plugin2 canary run .

Configuration File Plugins
--------------------------

Add plugins to configuration files:

.. code-block:: yaml

   canary:
     plugins:
       - my_plugin
       - another_plugin

Command-Line Plugins
--------------------

Load plugins directly from the command line with the global ``-p`` flag:

.. code-block:: console

   $ canary -p my_plugin run .

.. warning::

   ``-p`` is a **global** option and must appear **before** the subcommand.
   ``canary run -p my_plugin .`` does **not** load a plugin — the run-level
   ``-p`` is a parameter-expression filter, not a plugin loader.

   .. code-block:: console

      # CORRECT
      $ canary -p my_plugin run .

      # WRONG — run-level -p is a parameter filter
      $ canary run -p my_plugin .

Plugin Disabling
----------------

Disable plugins using ``no:`` prefix:

.. code-block:: console

   $ CANARY_PLUGINS=no:builtin.gpu_select canary run .

This prevents the GPU selection plugin from loading.

Plugin Registration
-------------------

Register plugins using the ``@canary.hookimpl`` decorator:

.. code-block:: python

   import canary

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("--my-option", help="Custom option")

Plugin Hooks
------------

Plugins implement hooks defined in Canary's hook specification. See :doc:`hooks` for complete reference.

Plugin Propagation to Workers and HPC Batch Children
-----------------------------------------------------

Plugins loaded via ``-p``, the ``plugins`` config key, or entry points are
automatically propagated to every execution context: the parent process,
spawned worker processes (``canary run``), and HPC batch children (``canary
hpc run``).  No extra configuration is needed.

How it works
~~~~~~~~~~~~

Before submitting an HPC batch or spawning a worker process, Canary serialises
its full configuration — including the list of loaded plugins — into a JSON
snapshot.  The child process receives this snapshot via the ``CANARYCFGFILE``
environment variable, restores the configuration, and re-loads every plugin
listed in it.

``PYTHONPATH`` is forwarded automatically with all relative entries resolved
to absolute paths against the invocation directory, so plugin modules that are
importable in the parent are importable in the child even when the child runs
from a different working directory (e.g. inside an HPC batch workspace).

If a plugin fails to load in a child process it is downgraded to a ``WARNING``
and the child continues without it — it does not crash the batch.  If you need
load failures to be hard errors, pass ``-p MODULE`` explicitly on the inner
``canary hpc exec`` invocation (rarely needed in practice).

Diagnosing hooks that do not fire in HPC jobs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If a ``canary_runtest_finish`` (or any other) hook appears not to run in a
Slurm/HPC batch job:

1. **Check the batch log** — errors loading or calling the plugin are logged at
   ``ERROR`` level in the per-batch JSON log file:

   .. code-block:: console

      $ canary hpc log BATCH_ID

2. **Verify PYTHONPATH** — the plugin module must be importable.  Run a quick
   local check:

   .. code-block:: console

      $ PYTHONPATH=src/hooks python -c "import my_plugin"

3. **Avoid module-level plugin registration** — do not call
   ``canary.config.pluginmanager.register(...)`` at module import time.  The
   plugin manager is rebuilt from the snapshot during child startup; any
   registrations made before ``load_snapshot()`` completes are discarded.  Use
   ``canary_addconfig`` instead (see :doc:`configuration`).

4. **Run with** ``-d`` **and inspect the JSON log** — debug-level hook
   lifecycle messages (``canary_runteststart: begin``, etc.) are written to
   ``.canary/logs/canary.<batch>.log``.

Debugging hook plugins
~~~~~~~~~~~~~~~~~~~~~~

During ``canary run``, ``logger.debug(...)`` calls inside plugin hooks execute
in spawned worker processes.  These debug records are **not** printed to the
terminal even with ``-d``/``--debug``.  They are routed only to the JSON log
file to avoid corrupting the live progress table.

To see debug output from a hook interactively:

- Use ``canary exec JOBID`` — this runs the job in-process with no worker
  pool, and all log levels reach the terminal.
- Use ``canary hpc log BATCH_ID`` to inspect the batch log after an HPC run.

Plugin Best Practices
---------------------

**Initialization**:

- Register hooks early in plugin lifecycle
- Avoid complex initialization in hook functions
- Use ``canary_addhooks`` for adding custom hooks

**Configuration**:

- Add options with ``canary_addoption``
- Validate configuration in ``canary_configure``
- Access options via ``canary.config.getoption()``

**Resource Management**:

- Clean up resources in ``canary_finish``
- Avoid memory leaks in long-running sessions
- Use context managers for resource handling

**Error Handling**:

- Provide meaningful error messages
- Use Canary's logging system
- Validate inputs before processing

**Performance**:

- Minimize overhead in frequently-called hooks
- Cache expensive computations
- Use lazy evaluation where appropriate

Plugin Examples
---------------

**Simple Option Plugin**:

.. code-block:: python

   import canary

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("--verbose-logging", action="store_true",
                          help="Enable verbose logging")

   @canary.hookimpl
   def canary_configure(config):
       if config.getoption("verbose_logging"):
           config.set_log_level("DEBUG")

**Job Masking Plugin**:

.. code-block:: python

   import canary

   EXCLUSION_LIST = ["slow_test1", "slow_test2"]

   @canary.hookimpl
   def canary_select_modifyitems(selector):
       for spec in selector.specs:
           if spec.name in EXCLUSION_LIST:
               spec.mask = canary.Mask.masked("Excluded by performance plugin")

**Environment Setup Plugin**:

.. code-block:: python

   import canary

   @canary.hookimpl
   def canary_runteststart(case):
       case.variables["CUSTOM_VAR"] = "value"

Plugin Development Workflow
---------------------------

1. **Create plugin module**: Start with simple hook implementations

2. **Test locally**: Use ``-p`` flag for rapid iteration

   .. code-block:: console

      $ canary -p my_plugin run .

3. **Add entry point**: Register for automatic discovery

4. **Package and distribute**: Create installable package

5. **Document behavior**: Explain plugin capabilities and usage

Plugin Troubleshooting
----------------------

**Plugin Not Loading**:

- Verify entry point registration
- Check module import path
- Ensure ``@canary.hookimpl`` decorator is used

**Hook Not Called**:

- Verify hook name matches specification
- Check plugin is loaded (use ``canary config show plugins``)
- Ensure no typos in hook function name

**Configuration Issues**:

- Verify option names match
- Check configuration precedence
- Validate option access timing

See Also
--------

- :doc:`hooks`: Comprehensive hook reference
- :doc:`generators`: Job generator development
- :doc:`commands`: Command extension
- :doc:`../user/configuration.overview`: Configuration management
