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
----------------------------------

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

Load plugins directly from command line:

.. code-block:: console

   $ canary -p my_plugin run .

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
   def canary_runtest_setup(job):
       job.environment["CUSTOM_VAR"] = "value"
       job.environment["PATH"] = "/custom/bin:" + job.environment.get("PATH", "")

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
- :doc:`../user/configuration`: Configuration management