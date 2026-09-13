.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-hooks:

Hooks
=====

Canary's hook system provides extension points throughout the execution lifecycle. Hooks allow plugins to integrate with Canary's workflow at specific phases.

Hook Lifecycle Groups
---------------------

Initialization Hooks
~~~~~~~~~~~~~~~~~~~~

**canary_addhooks**: Register additional hook specifications

.. code-block:: python

   @canary.hookimpl
   def canary_addhooks(pluginmanager):
       pluginmanager.add_hookspecs(my_hooks_module)

**canary_addoption**: Add command-line options

.. code-block:: python

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("--my-option", help="Custom option")

**canary_addcommand**: Add subcommands

.. code-block:: python

   @canary.hookimpl
   def canary_addcommand(parser):
       parser.add_command(MyCommand())

**canary_addconfig**: Add configuration sections

.. code-block:: python

   @canary.hookimpl
   def canary_addconfig(config):
       config.data["my_section"] = {"key": "value"}

**canary_configure**: Perform initial configuration

.. code-block:: python

   @canary.hookimpl
   def canary_configure(config):
       # Validate and modify configuration
       pass

**canary_finish**: Clean up after configuration

.. code-block:: python

   @canary.hookimpl
   def canary_finish(config):
       # Release resources
       pass

Session Hooks
~~~~~~~~~~~~~

**canary_sessionstart**: Called when session begins

.. code-block:: python

   @canary.hookimpl
   def canary_sessionstart(session):
       session.add_measurement("session_start", time.time())

**canary_sessionfinish**: Called when session completes

.. code-block:: python

   @canary.hookimpl
   def canary_sessionfinish(session):
       session.add_measurement("session_duration", calculate_duration())

Collection Hooks
~~~~~~~~~~~~~~~~

**canary_collectstart**: Start collection phase

.. code-block:: python

   @canary.hookimpl
   def canary_collectstart(collector):
       collector.add_skip_dirs([".git", "build"])

**canary_collect_modifyitems**: Modify collected items

.. code-block:: python

   @canary.hookimpl
   def canary_collect_modifyitems(collector):
       # Filter or reorder collected items
       pass

**canary_collect_report**: Generate collection report

.. code-block:: python

   @canary.hookimpl
   def canary_collect_report(collector):
       print(f"Collected {len(collector.items)} items")

**canary_testcase_generator**: Provide custom generators

.. code-block:: python

   @canary.hookimpl
   def canary_testcase_generator(root, path):
       if path.endswith(".myformat"):
           return MyGenerator(root, path)

Generation Hooks
~~~~~~~~~~~~~~~~

**canary_generate_modifyitems**: Modify generated job specs

.. code-block:: python

   @canary.hookimpl
   def canary_generate_modifyitems(generator):
       for spec in generator.specs:
           # Modify job specifications
           pass

Selection Hooks
~~~~~~~~~~~~~~~

**canary_select_modifyitems**: Modify selection

.. code-block:: python

   @canary.hookimpl
   def canary_select_modifyitems(selector):
       for spec in selector.specs:
           if should_mask(spec):
               spec.mask = canary.Mask.masked("Reason")

Runtime Selection Hooks
~~~~~~~~~~~~~~~~~~~~~~~

**canary_runtest_setup**: Setup before test execution

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_setup(job):
       # Setup test environment
       pass

**canary_runtest_finish**: Cleanup after test execution

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_finish(job):
       # Process test results
       job.add_measurement("custom_metric", calculate_metric())

Execution Hooks
~~~~~~~~~~~~~~~

**canary_execute_modifyitems**: Modify execution plan

.. code-block:: python

   @canary.hookimpl
   def canary_execute_modifyitems(executor):
       # Adjust execution order or parameters
       pass

Resource Pool Hooks
~~~~~~~~~~~~~~~~~~~

**canary_resource_pool_fill**: Create resource pool

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_fill(config):
       return {"nodes": [{"id": "node1", "resources": {...}}]}

**canary_resource_pool_update**: Modify resource pool

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_update(config, pool):
       # Add custom resources to pool
       pass

**canary_resource_pool_accommodates**: Check resource availability

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_accommodates(pool, request):
       # Custom accommodation logic
       pass

Hook Types and Behavior
-----------------------

**Regular Hooks**: Multiple implementations can run

.. code-block:: python

   @canary.hookimpl
   def canary_sessionstart(session):
       # Multiple plugins can implement this
       pass

**First-Result Hooks**: First non-None result wins

.. code-block:: python

   @canary.hookimpl(firstresult=True)
   def canary_testcase_generator(root, path):
       # First matching generator wins
       pass

**Wrapper Hooks**: Wrap other hook implementations

.. code-block:: python

   @canary.hookimpl(hookwrapper=True)
   def canary_runtest_setup(job):
       # Setup before other hooks
       yield
       # Cleanup after other hooks

Hook Ordering
-------------

Hooks execute in registration order unless specified otherwise. Use ``tryfirst`` and ``trylast`` for ordering control:

.. code-block:: python

   @canary.hookimpl(tryfirst=True)
   def canary_sessionstart(session):
       # Run this hook first
       pass

   @canary.hookimpl(trylast=True)
   def canary_sessionstart(session):
       # Run this hook last
       pass

Hook Best Practices
-------------------

**Source Compatibility**:

- Avoid mutating objects outside intended lifecycle
- Use immutable data structures where possible
- Document hook dependencies and side effects

**Error Handling**:

- Validate inputs before processing
- Provide meaningful error messages
- Use Canary's logging system for debugging

**Performance**:

- Minimize overhead in frequently-called hooks
- Cache expensive computations
- Use lazy evaluation for optional functionality

**Documentation**:

- Document hook purpose and usage
- Provide examples of hook implementations
- Explain expected return values and side effects

Hook Examples
-------------

**Configuration Validation Hook**:

.. code-block:: python

   @canary.hookimpl
   def canary_configure(config):
       required_option = config.getoption("required_option")
       if not required_option:
           raise ValueError("required_option must be set")

**Test Duration Measurement Hook**:

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_finish(job):
       duration = job.timekeeper.duration()
       if duration > 60.0:
           job.add_measurement("long_running", True)

**Resource Monitoring Hook**:

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_setup(job):
       # Record initial resource usage
       job.add_measurement("initial_memory", get_memory_usage())

   @canary.hookimpl
   def canary_runtest_finish(job):
       # Record final resource usage
       job.add_measurement("final_memory", get_memory_usage())

Hook Troubleshooting
--------------------

**Hook Not Called**:

- Verify hook name matches specification exactly
- Check plugin is loaded (``canary config show plugins``)
- Ensure correct decorator (``@canary.hookimpl``)

**Wrong Hook Order**:

- Use ``tryfirst``/``trylast`` for ordering control
- Check registration order
- Verify no conflicting hooks

**Performance Issues**:

- Profile hook execution time
- Optimize expensive operations
- Consider caching strategies

See Also
--------

- :doc:`plugins`: Plugin loading and management
- :doc:`generators`: Job generator hooks
- :doc:`commands`: Command extension hooks
- :doc:`../user/concepts`: Core Canary concepts