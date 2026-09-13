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

**canary_addconfig**: Add configuration sections

.. code-block:: python

   @canary.hookimpl
   def canary_addconfig(config):
       config.data["my_section"] = {"key": "default_value"}

**canary_configure**: Modify configuration

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

Configuration Examples
----------------------

**Resource Configuration Plugin**:

.. code-block:: python

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("--custom-resource", help="Custom resource type")

   @canary.hookimpl
   def canary_addconfig(config):
       config.data["custom_resources"] = {
           "accelerators": config.getoption("custom_resource") or []
       }

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

   @canary.hookimpl
   def canary_addconfig(config):
       # Merge with existing configuration
       existing = config.data.get("my_section", {})
       config.data["my_section"] = {**existing, **new_config}

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