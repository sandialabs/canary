.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-configuration:

Configuration
=============

Extensions can add custom configuration options and modify Canary's configuration system. Configuration extensions integrate with Canary's layered configuration model.

Configuration Hooks
-------------------

**canary_addoption**: Add command-line options

.. code-block:: python

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("--my-option", help="Custom option")

**canary_addconfig**: Register configuration sections and schemas

``canary_addconfig`` fires early in every startup path — including inside
spawned worker processes and HPC batch children that restore from a config
snapshot.  It is the correct place to:

- Register a config section with a schema via ``config.add_section()``.
- Register additional plugin objects that must exist in every execution
  context (see :ref:`registering-extra-plugin-objects` below).

Do **not** use ``canary_addconfig`` to read command-line options; those are
not yet parsed when this hook fires.

.. code-block:: python

   import canary
   from canary import schema  # or voluptuous / jsonschema, etc.

   MY_SCHEMA = {
       "enabled": bool,
       "threshold": float,
   }

   @canary.hookimpl
   def canary_addconfig(config):
       config.add_section(name="my_plugin", schema=MY_SCHEMA)

**canary_configure**: Validate and apply configuration after option parsing

``canary_configure`` fires after command-line arguments have been parsed.
Use it to read options, validate them, and trigger any side effects that
depend on the parsed values.

.. code-block:: python

   @canary.hookimpl
   def canary_configure(config):
       # Validate and modify configuration
       if "my_option" not in config.data:
           config.data["my_option"] = "default"

Plugin Options
--------------

Add plugin-specific configuration options:

.. code-block:: python

   @canary.hookimpl
   def canary_addoption(parser):
       group = parser.add_argument_group("My Plugin Options")
       group.add_argument("--plugin-enable", action="store_true")
       group.add_argument("--plugin-timeout", type=float, default=30.0)

Configuration Access
--------------------

Access configuration values in hooks:

.. code-block:: python

   @canary.hookimpl
   def canary_sessionstart(session):
       enabled = canary.config.getoption("plugin_enable")
       timeout = canary.config.getoption("plugin_timeout")

Configuration Validation
------------------------

Validate configuration in ``canary_configure``:

.. code-block:: python

   @canary.hookimpl
   def canary_configure(config):
       timeout = config.getoption("plugin_timeout")
       if timeout <= 0:
           raise ValueError("plugin_timeout must be positive")

       if timeout > 3600:
           config.logger.warning("Very long plugin timeout: %s", timeout)

Configuration Aliases
---------------------

Create configuration aliases for convenience:

.. code-block:: python

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("-t", "--timeout", dest="plugin_timeout")

Environment Variables
---------------------

Add environment variable support:

.. code-block:: python

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("--my-option",
                          default=os.environ.get("MY_OPTION", "default"))

Configuration Best Practices
----------------------------

**Layered Configuration**:

- Support multiple configuration sources
- Allow command-line overrides
- Provide sensible defaults

**Validation**:

- Validate early in ``canary_configure``
- Provide meaningful error messages
- Use Canary's logging system

**Documentation**:

- Document configuration options
- Provide examples
- Explain interactions

.. _registering-extra-plugin-objects:

Registering Extra Plugin Objects
---------------------------------

A plugin *module* can only supply one function per hook name.  When you need
multiple independent implementations of the same hook (e.g. several
``canary_runtest_finish`` post-processors), register them as separate plugin
objects via ``canary_addconfig``:

.. code-block:: python

   import canary

   class _MyExtraPostprocessor:
       @canary.hookimpl
       def canary_runtest_finish(self, case):
           case.add_measurement("extra_metric", compute_metric(case))

   @canary.hookimpl
   def canary_addconfig(config):
       pm = config.pluginmanager
       if not pm.get_plugin("my_extra_postprocessor"):
           pm.register(_MyExtraPostprocessor(), name="my_extra_postprocessor")

The ``if not pm.get_plugin(...)`` guard prevents double-registration because
``canary_addconfig`` fires once per plugin registration and the module itself
is also a plugin.

.. warning::

   Do **not** call ``canary.config.pluginmanager.register(...)`` at module
   import time.  When Canary restores a config snapshot in a worker process or
   HPC batch child, it rebuilds the plugin manager from scratch.  Any
   registrations made at import time — before ``load_snapshot()`` completes —
   are made against the old plugin manager and are silently discarded.
   ``canary_addconfig`` is called after the new plugin manager is ready and is
   the safe alternative.

Configuration Examples
----------------------

**Resource Configuration Plugin**:

.. code-block:: python

   MY_RESOURCE_SCHEMA = {"accelerators": list}

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("--custom-resource", help="Custom resource type")

   @canary.hookimpl
   def canary_addconfig(config):
       config.add_section(name="custom_resources", schema=MY_RESOURCE_SCHEMA)

**Timeout Configuration Plugin**:

.. code-block:: python

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("--extended-timeout", type=float,
                          help="Extended timeout for specific tests")

   @canary.hookimpl
   def canary_configure(config):
       extended = config.getoption("extended_timeout")
       if extended:
           config.data["timeout"]["extended"] = extended

Configuration Integration
-------------------------

**Configuration Precedence**:

- Command line overrides environment
- Environment overrides config files
- Config files override defaults

**Configuration Merging**:

.. code-block:: python

   MY_SECTION_SCHEMA = {"key": str, "extra": str}

   @canary.hookimpl
   def canary_addconfig(config):
       config.add_section(name="my_section", schema=MY_SECTION_SCHEMA)

Configuration Troubleshooting
-----------------------------

**Option Not Found**:

- Verify option name in ``canary_addoption``
- Check configuration precedence
- Ensure plugin is loaded

**Validation Errors**:

- Check validation logic
- Verify input ranges and types
- Test with different values

**Configuration Conflicts**:

- Check for overlapping option names
- Verify precedence order
- Test configuration merging

See Also
--------

- :doc:`plugins`: Plugin configuration
- :doc:`hooks`: Configuration hooks
- :doc:`../user/configuration`: Core configuration
- :doc:`/reference/commands.config`: Config command