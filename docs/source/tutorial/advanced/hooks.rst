.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-hooks:

Canary Hooks: Extending Test Behavior
=====================================

Hooks are one of Canary's most powerful features, allowing you to customize behavior
at every stage of test execution. This tutorial covers the most commonly used hooks
with practical examples.

Hook Overview
-------------

Canary uses the `pluggy <https://pluggy.readthedocs.io>`_ hook system to provide
extension points throughout the test lifecycle. Hooks allow you to:

- **Modify test behavior** before, during, and after execution
- **Add custom measurements** and metadata to tests
- **Integrate with external systems** (logging, monitoring, CI/CD)
- **Implement custom resource management** and execution strategies

Common Hook Types
-----------------

1. **Session Hooks**: Run at session start/end
2. **Test Hooks**: Run before/after individual tests
3. **Execution Hooks**: Control test execution flow
4. **Resource Hooks**: Manage resource allocation

Session Lifecycle Hooks
-----------------------

Session Start Hook
^^^^^^^^^^^^^^^^^^

The ``canary_sessionstart`` hook runs when a new session begins:

.. code-block:: python
   :caption: Session startup hook

   from _canary.hookspec import hookimpl
   
   @hookimpl
   def canary_sessionstart(session):
       """Initialize session-level resources and metadata."""
       
       # Add session metadata
       session.add_measurement("environment", "production")
       session.add_measurement("start_time", datetime.now().isoformat())
       
       # Initialize external systems
       logging.setup_session_logging(session.name)
       monitoring.start_session(session.id)
       
       # Configure session behavior
       session.config["custom_timeout_factor"] = 1.5

Session Finish Hook
^^^^^^^^^^^^^^^^^^^

The ``canary_sessionfinish`` hook runs after all tests complete:

.. code-block:: python
   :caption: Session cleanup hook

   @hookimpl
   def canary_sessionfinish(session):
       """Clean up resources and finalize session data."""
       
       # Calculate session metrics
       total_tests = len(session.jobs)
       passed_tests = sum(1 for j in session.jobs if j.status.category == "PASS")
       
       session.add_measurement("test_count", total_tests)
       session.add_measurement("pass_rate", passed_tests / total_tests)
       
       # Notify external systems
       monitoring.end_session(session.id)
       reporting.send_session_report(session)
       
       # Archive results
       if session.config.get("archive_results"):
           archive.upload_session_results(session)

Test Lifecycle Hooks (Most Common!)
-----------------------------------

Pre-Test Setup Hook
^^^^^^^^^^^^^^^^^^^

The ``canary_runtest_setup`` hook runs before each test executes:

.. code-block:: python
   :caption: Pre-test setup hook

   @hookimpl
   def canary_runtest_setup(job):
       """Prepare test environment and resources."""
       
       # Set up test-specific environment
       job.variables["TEST_START_TIME"] = datetime.now().isoformat()
       job.variables["TEST_TEMP_DIR"] = tempfile.mkdtemp()
       
       # Initialize test-specific resources
       db_connection = create_test_database()
       job.variables["DB_CONNECTION"] = db_connection
       
       # Add pre-test metadata
       job.add_measurement("setup_duration", 0.123)
       
       # Log test start
       logger.info(f"Starting test {job.id}: {job.name}")

Post-Test Finish Hook
^^^^^^^^^^^^^^^^^^^^^

The ``canary_runtest_finish`` hook runs after each test completes:

.. code-block:: python
   :caption: Post-test cleanup hook

   @hookimpl
   def canary_runtest_finish(job):
       """Process test results and clean up resources."""
       
       # Calculate test duration
       duration = job.timekeeper.total
       job.add_measurement("test_duration", duration)
       
       # Process test outputs
       if job.status.category == "PASS":
           results = parse_test_output(job)
           job.add_measurement("custom_metrics", results)
       
       # Clean up resources
       db_connection = job.variables.get("DB_CONNECTION")
       if db_connection:
           db_connection.close()
       
       temp_dir = job.variables.get("TEST_TEMP_DIR")
       if temp_dir:
           shutil.rmtree(temp_dir)
       
       # Log test completion
       logger.info(f"Completed test {job.id}: {job.status.outcome}")

Wrapper Hooks for Advanced Control
-----------------------------------

Wrapper hooks allow you to run code before and after other hooks:

.. code-block:: python
   :caption: Wrapper hook for timing

   @hookimpl(hookwrapper=True)
   def canary_runtest_setup(job):
       """Time the entire setup phase."""
       
       # Code runs BEFORE other setup hooks
       start_time = time.time()
       
       # Yield to other hook implementations
       yield
       
       # Code runs AFTER other setup hooks
       setup_duration = time.time() - start_time
       job.add_measurement("setup_time", setup_duration)

Practical Hook Examples
-----------------------

Example 1: Test Duration Monitoring
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python
   :caption: Monitoring test durations

   @hookimpl
   def canary_runtest_finish(job):
       """Monitor and alert on slow tests."""
       
       duration = job.timekeeper.running
       threshold = 30.0  # 30 seconds
       
       if duration > threshold:
           alert.send_slow_test_alert(
               test_id=job.id,
               test_name=job.name,
               duration=duration,
               threshold=threshold
           )
           
       job.add_measurement("duration_monitored", True)

Example 2: Resource Usage Tracking
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python
   :caption: Track resource usage

   @hookimpl
   def canary_runtest_finish(job):
       """Track CPU and memory usage."""
       
       # Get resource usage
       cpu_percent = psutil.cpu_percent()
       memory_info = psutil.virtual_memory()
       
       job.add_measurement("cpu_usage", cpu_percent)
       job.add_measurement("memory_usage", memory_info.percent)
       job.add_measurement("memory_available", memory_info.available)

Example 3: External System Integration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python
   :caption: Integrate with test management system

   @hookimpl
   def canary_runtest_finish(job):
       """Send results to external test management system."""
       
       result = {
           "test_id": job.id,
           "test_name": job.name,
           "status": job.status.outcome,
           "duration": job.timekeeper.total,
           "timestamp": datetime.now().isoformat(),
           "measurements": dict(job.measurements.data)
       }
       
       try:
           response = requests.post(
               "https://test-management.example.com/api/results",
               json=result,
               timeout=10
           )
           response.raise_for_status()
           job.add_measurement("external_report_success", True)
       except Exception as e:
           logger.error(f"Failed to report to external system: {e}")
           job.add_measurement("external_report_success", False)

Example 4: Test Retry Logic
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python
   :caption: Automatic retry for flaky tests

   @hookimpl
   def canary_runtest_finish(job):
       """Automatically retry flaky tests."""
       
       if should_retry(job):
           retry_count = job.meta.get("retry_count", 0) + 1
           
           if retry_count <= 3:  # Max 3 retries
               job.meta["retry_count"] = retry_count
               job.status = Status("PENDING", "RETRY")
               logger.info(f"Retrying test {job.id} (attempt {retry_count})")
           else:
               logger.warning(f"Test {job.id} failed after 3 retries")

Best Practices for Hooks
------------------------

1. **Keep hooks focused**: Each hook should do one thing well
2. **Handle errors gracefully**: Don't let hook failures break tests
3. **Add measurements**: Record hook activity for debugging
4. **Log appropriately**: Use different log levels (info, warning, error)
5. **Respect performance**: Avoid slow operations in critical hooks
6. **Document behavior**: Add docstrings explaining hook purpose
7. **Test hooks**: Write tests for your hook implementations
8. **Use configuration**: Make hooks configurable via settings

Common Hook Patterns
--------------------

Pattern 1: Conditional Hook Execution
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_setup(job):
       # Only run for specific test types
       if "performance" in job.keywords:
           setup_performance_monitoring()

Pattern 2: Hook Chaining
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl(tryfirst=True)
   def canary_runtest_setup(job):
       # Runs before other setup hooks
       initialize_base_resources()

   @hookimpl(trylast=True)
   def canary_runtest_setup(job):
       # Runs after other setup hooks
       finalize_setup()

Pattern 3: Context Management
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_setup(job):
       # Store context for later use
       context = create_test_context()
       job.variables["test_context"] = context

   @hookimpl
   def canary_runtest_finish(job):
       # Retrieve and use context
       context = job.variables.get("test_context")
       if context:
           cleanup_context(context)

Debugging Hooks
---------------

Debugging hook execution can be challenging. Use these techniques:

.. code-block:: python

   # Enable debug logging
   logger = logging.getLogger(__name__)
   logger.setLevel(logging.DEBUG)
   
   # Add detailed logging
   @hookimpl
   def canary_runtest_setup(job):
       logger.debug(f"Setup hook called for {job.id}")
       logger.debug(f"Current job variables: {dict(job.variables)}")
       
       # Add timing information
       start = time.time()
       yield  # For wrapper hooks
       duration = time.time() - start
       logger.debug(f"Setup hook took {duration:.3f}s")

Hook Discovery and Registration
-------------------------------

To make Canary discover your hooks, use one of these methods:

Method 1: Entry Points (Recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In your ``setup.py`` or ``pyproject.toml``:

.. code-block:: toml
   :caption: pyproject.toml

   [project.entry-points.canary]
   my_plugin = "my_plugin.module"

Method 2: Direct Registration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from _canary.pluginmanager import CanaryPluginManager
   
   pluginmanager = CanaryPluginManager.factory()
   pluginmanager.register(my_hook_module)

Method 3: Command Line
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: console

   python3 -m canary --plugins my_plugin run tests

.. seealso::

   - :doc:`/extending/hooks`: Complete hook reference
   - :doc:`/extensions/pyt/directives`: Python test directives
   - :doc:`/user/workflows`: Workflow automation patterns
   - :doc:`/api/hooks`: Hook API reference