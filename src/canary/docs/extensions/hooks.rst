.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-hooks:

Hooks
=====

Canary's hook system provides extension points throughout the execution lifecycle. Hooks allow plugins to integrate with Canary's workflow at specific phases.

Hook Reference Table
--------------------

The table below lists every hookspec with its ``firstresult`` setting and the
default implementation ordering.  ``firstresult=True`` means only the first
non-``None`` return value is used; ``firstresult=False`` (the default) means
every implementation runs.

.. list-table::
   :header-rows: 1
   :widths: 35 12 18 35

   * - Hook
     - firstresult
     - Default impl
     - Purpose
   * - ``canary_addhooks``
     - False
     - —
     - Register additional hookspecs
   * - ``canary_addoption``
     - False
     - —
     - Add command-line options
   * - ``canary_addcommand``
     - False
     - —
     - Add CLI subcommands
   * - ``canary_addconfig``
     - False
     - —
     - Register config sections/schemas; register extra plugin objects
   * - ``canary_configure``
     - False
     - —
     - Validate/apply config after option parsing
   * - ``canary_finish``
     - False
     - —
     - Clean up after a session
   * - ``canary_cmdline_parse``
     - **True**
     - —
     - Override command-line parsing
   * - ``canary_cmdline_modifyargs``
     - False
     - —
     - Modify parsed args
   * - ``canary_addcommand``
     - False
     - —
     - Add a CLI subcommand
   * - ``canary_query_subcommand``
     - False
     - —
     - Add a ``canary query`` subcommand
   * - ``canary_query_execute``
     - **True**
     - —
     - Execute a ``canary query`` subcommand
   * - ``canary_fetch_subcommand``
     - False
     - —
     - Register a fetchable asset
   * - ``canary_fetch_execute``
     - **True**
     - —
     - Execute a ``canary fetch`` request
   * - ``canary_capabilities``
     - False
     - —
     - Contribute to ``canary learn capabilities``
   * - ``canary_skills``
     - False
     - —
     - Contribute to ``canary learn skills``
   * - ``canary_sessionstart``
     - False
     - —
     - Session started
   * - ``canary_sessionfinish``
     - False
     - —
     - Session finished
   * - ``canary_collectstart``
     - False
     - —
     - Collection phase started
   * - ``canary_collect_modifyitems``
     - False
     - —
     - Filter/reorder collected files
   * - ``canary_collect_report``
     - False
     - —
     - Report collection results
   * - ``canary_testcase_generator``
     - **True**
     - —
     - Return a generator for a file
   * - ``canary_generatestart``
     - False
     - —
     - Generation phase started
   * - ``canary_generate_modifyitems``
     - False
     - —
     - Filter/modify generated specs
   * - ``canary_generate_report``
     - False
     - —
     - Report generation results
   * - ``canary_selectstart``
     - False
     - —
     - Selection phase started
   * - ``canary_select_modifyitems``
     - False
     - —
     - Filter/mask specs at selection time
   * - ``canary_rtselectstart``
     - False
     - —
     - Runtime selection started
   * - ``canary_rtselect_modifyitems``
     - False
     - —
     - Filter/mask specs at runtime
   * - ``canary_runtests_start``
     - False
     - —
     - Test session execution started
   * - ``canary_runtests``
     - **True**
     - trylast (default runner)
     - Provide a test-session execution backend
   * - ``canary_runtests_report``
     - False
     - —
     - Session-level reporting
   * - ``canary_runtest_launcher``
     - **True**
     - —
     - Return a launcher for a specific job
   * - ``canary_runteststart``
     - False
     - tryfirst (built-in setup)
     - Per-job setup; runs before the job command
   * - ``canary_runtest``
     - **True**
     - trylast (default runner)
     - Execute the job command
   * - ``canary_runtest_finish``
     - False
     - tryfirst (built-in finish)
     - Per-job post-processing; runs after the job command
   * - ``canary_runtest_rebaseline``
     - False
     - trylast (built-in rebaseline)
     - Rebaseline a job from its results
   * - ``canary_resource_pool_fill``
     - **True**
     - —
     - Provide the initial resource pool
   * - ``canary_resource_pool_update``
     - False
     - —
     - Augment/mutate the resource pool
   * - ``canary_resource_pool_accommodates``
     - **True**
     - —
     - Check whether a job can be accommodated
   * - ``canary_resource_pool_types``
     - **True**
     - —
     - Return available resource type names

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

Execution Hooks
~~~~~~~~~~~~~~~

**canary_runteststart**: Setup before test execution (``firstresult=False``)

Called inside the job's working directory before the job command runs.  Every
registered implementation fires.  The built-in default (``tryfirst``) creates
the workspace and calls ``case.setup()``.  Plugin implementations run
afterwards and may write files into the workspace or set ``case.variables``.

.. code-block:: python

   @canary.hookimpl
   def canary_runteststart(case):
       # e.g. write an input file into the job workspace before execution
       pass

**canary_runtest**: Execute the job (``firstresult=True``)

The first non-``None`` return claims execution.  The built-in runner is
registered ``trylast`` so plugins may override how a job is executed.  Return
``None`` to fall through to the default runner.

**canary_runtest_finish**: Post-processing after test execution (``firstresult=False``)

Called inside the job's working directory after the job command finishes.
Every registered implementation fires — this is a broadcast hook, not
first-result.  The built-in default (``tryfirst``) calls ``case.finish()`` and
saves the job first; plugin implementations run afterwards.  Use
``@canary.hookimpl(trylast=True)`` to guarantee your implementation runs after
all other registered finish hooks.

.. code-block:: python

   @canary.hookimpl(trylast=True)
   def canary_runtest_finish(case):
       # Post-process results, read output files, add measurements
       case.add_measurement("custom_metric", calculate_metric())

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

   @canary.hookimpl
   def canary_testcase_generator(root, path):
       # First matching generator wins; return None to pass to the next
       if path and path.endswith(".myformat"):
           return MyGenerator(root, path)
       return None

**Wrapper Hooks**: Wrap other hook implementations

.. code-block:: python

   @canary.hookimpl(hookwrapper=True)
   def canary_runteststart(case):
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
   def canary_runteststart(case):
       # Record initial resource usage before the job runs
       case.add_measurement("initial_memory", get_memory_usage())

   @canary.hookimpl(trylast=True)
   def canary_runtest_finish(case):
       # Record final resource usage after the job runs
       case.add_measurement("final_memory", get_memory_usage())

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