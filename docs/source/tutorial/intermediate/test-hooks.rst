.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-test-hooks:

Pre and Post Test Hooks: Practical Guide
========================================

This tutorial focuses on the **most commonly used hooks** in Canary: ``canary_runtest_setup``
and ``canary_runtest_finish``. These hooks allow you to customize behavior before and after
each test execution.

Why Use Test Hooks?
-------------------

Test hooks enable powerful workflows:

- **Setup test environment** (files, databases, services)
- **Inject test data** (parameters, configurations)
- **Capture test metrics** (performance, coverage)
- **Process test outputs** (logs, artifacts, results)
- **Integrate with external systems** (CI/CD, monitoring)
- **Implement custom logic** (retries, validations)

Basic Test Hook Structure
-------------------------

A complete test with hooks looks like this:

.. code-block:: python
   :caption: Test with hooks

   # test_with_hooks.pyt
   import canary
   import canary_pyt
   
   canary_pyt.directives.keywords("hooks", "demo")
   
   def main():
       instance = canary.get_instance()
       
       # Access hook-provided data
       config = instance.variables.get("test_config")
       temp_dir = instance.variables.get("temp_directory")
       
       # Run the actual test
       result = run_test_logic(config)
       
       # Test completes normally
       print(f"Test result: {result}")

Pre-Test Setup Hook
-------------------

The setup hook runs **before** your test's ``main()`` function:

.. code-block:: python
   :caption: Basic setup hook

   from _canary.hookspec import hookimpl
   import tempfile
   import os
   
   @hookimpl
   def canary_runtest_setup(job):
       """Prepare everything needed for the test."""
       
       # Create temporary directory
       temp_dir = tempfile.mkdtemp(prefix=f"test_{job.id}_")
       job.variables["temp_directory"] = temp_dir
       
       # Create input files
       input_file = os.path.join(temp_dir, "input.txt")
       with open(input_file, "w") as f:
           f.write("Test input data\n")
       
       # Set configuration
       job.variables["test_config"] = {
           "timeout": 30,
           "retries": 3,
           "debug": False
       }
       
       # Add setup metadata
       job.add_measurement("setup_complete", True)
       job.add_measurement("temp_dir_created", temp_dir)

Post-Test Finish Hook
---------------------

The finish hook runs **after** your test completes (success or failure):

.. code-block:: python
   :caption: Basic finish hook

   @hookimpl
   def canary_runtest_finish(job):
       """Clean up and process results."""
       
       # Get test results
       status = job.status.outcome
       duration = job.timekeeper.total
       
       # Process output files
       temp_dir = job.variables.get("temp_directory")
       if temp_dir and os.path.exists(temp_dir):
           output_file = os.path.join(temp_dir, "output.txt")
           if os.path.exists(output_file):
               with open(output_file, "r") as f:
                   output = f.read()
               job.add_measurement("output_size", len(output))
       
       # Clean up
       if temp_dir and os.path.exists(temp_dir):
           import shutil
           shutil.rmtree(temp_dir)
       
       # Add final metadata
       job.add_measurement("test_completed", True)
       job.add_measurement("final_status", status)

Common Setup Hook Patterns
--------------------------

Pattern 1: File Setup
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_setup(job):
       # Copy test data files
       test_data = job.variables.get("test_data")
       if test_data:
           for src, dst in test_data.items():
               shutil.copy(src, dst)
               job.add_measurement(f"copied_{os.path.basename(dst)}", True)

Pattern 2: Database Setup
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_setup(job):
       # Create test database
       db_name = f"testdb_{job.id}"
       connection = create_database(db_name)
       
       # Store connection for test use
       job.variables["db_connection"] = connection
       
       # Initialize schema
       initialize_schema(connection)
       
       # Add cleanup info
       job.variables["db_name"] = db_name

Pattern 3: Service Mocking
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_setup(job):
       # Start mock services
       mock_server = start_mock_api_server(port=8080 + hash(job.id) % 1000)
       job.variables["mock_server"] = mock_server
       
       # Configure test to use mock
       job.variables["api_endpoint"] = mock_server.url

Pattern 4: Test Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_setup(job):
       # Load configuration based on keywords
       if "performance" in job.keywords:
           config = load_performance_config()
       elif "unit" in job.keywords:
           config = load_unit_test_config()
       else:
           config = load_default_config()
       
       job.variables["test_config"] = config

Common Finish Hook Patterns
---------------------------

Pattern 1: Result Processing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_finish(job):
       # Parse and validate output
       if job.status.category == "PASS":
           results = parse_test_output(job)
           validate_results(results)
           job.add_measurement("validation_passed", True)
       else:
           error_details = analyze_failure(job)
           job.add_measurement("failure_reason", error_details)

Pattern 2: Artifact Collection
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_finish(job):
       # Collect and save artifacts
       artifacts = [
           "output.json",
           "test.log",
           "screenshots/*.png"
       ]
       
       for pattern in artifacts:
           for file in glob.glob(pattern):
               if os.path.exists(file):
                   shutil.copy(file, job.artifacts_dir)
                   job.add_measurement("artifacts_collected", 
                                     job.add_measurement.get("artifacts_collected", 0) + 1)

Pattern 3: External Reporting
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_finish(job):
       # Send results to external systems
       result_data = {
           "test_id": job.id,
           "test_name": job.name,
           "status": job.status.outcome,
           "duration": job.timekeeper.total,
           "measurements": dict(job.measurements.data)
       }
       
       send_to_monitoring_system(result_data)
       send_to_ci_system(result_data)

Pattern 4: Resource Cleanup
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_finish(job):
       # Clean up all resources
       db_conn = job.variables.get("db_connection")
       if db_conn:
           db_conn.close()
       
       temp_files = job.variables.get("temp_files", [])
       for file in temp_files:
           if os.path.exists(file):
               os.remove(file)

Complete Example: Data Processing Workflow
------------------------------------------

Here's a complete example showing setup and finish hooks working together:

.. code-block:: python
   :caption: data_processor.pyt

   import canary
   import canary_pyt
   
   canary_pyt.directives.keywords("data", "processing")
   canary_pyt.directives.description("Data processing test with hooks")
   
   def main():
       instance = canary.get_instance()
       
       # Get setup data
       input_file = instance.variables["input_file"]
       output_file = instance.variables["output_file"]
       config = instance.variables["processing_config"]
       
       # Process data
       with open(input_file, "r") as f:
           data = f.read()
       
       processed = process_data(data, **config)
       
       # Save results
       with open(output_file, "w") as f:
           f.write(processed)
       
       # Add test measurements
       instance.add_measurement("input_size", len(data))
       instance.add_measurement("output_size", len(processed))
       instance.add_measurement("processing_ratio", len(processed) / len(data))

.. code-block:: python
   :caption: Hooks for data processor

   @hookimpl
   def canary_runtest_setup(job):
       """Setup data processing test."""
       
       # Create temporary files
       temp_dir = tempfile.mkdtemp()
       input_file = os.path.join(temp_dir, "input.dat")
       output_file = os.path.join(temp_dir, "output.dat")
       
       # Generate test data
       test_data = generate_test_data(job.parameters.get("size", 1000))
       with open(input_file, "w") as f:
           f.write(test_data)
       
       # Store paths for test
       job.variables["input_file"] = input_file
       job.variables["output_file"] = output_file
       job.variables["temp_dir"] = temp_dir
       
       # Set processing configuration
       job.variables["processing_config"] = {
           "algorithm": job.parameters.get("algorithm", "default"),
           "optimize": job.parameters.get("optimize", True),
           "debug": "debug" in job.keywords
       }
       
       job.add_measurement("setup_complete", True)

   @hookimpl
   def canary_runtest_finish(job):
       """Process data processing results."""
       
       # Get results
       output_file = job.variables.get("output_file")
       temp_dir = job.variables.get("temp_dir")
       
       if output_file and os.path.exists(output_file):
           # Validate output
           with open(output_file, "r") as f:
               result = f.read()
           
           validation = validate_output(result)
           job.add_measurement("validation_passed", validation)
           
           # Save as artifact if validation passed
           if validation:
               shutil.copy(output_file, job.artifacts_dir)
               job.add_measurement("artifact_saved", True)
       
       # Clean up
       if temp_dir and os.path.exists(temp_dir):
           shutil.rmtree(temp_dir)
       
       job.add_measurement("cleanup_complete", True)

Debugging Hooks
---------------

Debugging hook issues can be tricky. Use these techniques:

.. code-block:: python

   @hookimpl
   def canary_runtest_setup(job):
       import logging
       logger = logging.getLogger(__name__)
       
       # Debug logging
       logger.debug(f"Setting up test {job.id}: {job.name}")
       logger.debug(f"Current variables: {dict(job.variables)}")
       logger.debug(f"Job parameters: {dict(job.parameters)}")
       
       try:
           # Your setup code
           result = setup_resources()
           logger.info(f"Setup completed successfully for {job.id}")
           return result
       except Exception as e:
           logger.error(f"Setup failed for {job.id}: {e}")
           job.add_measurement("setup_error", str(e))
           raise

Hook Best Practices
-------------------

1. **Idempotent Setup**: Ensure setup can run multiple times safely
2. **Complete Cleanup**: Always clean up resources in finish hooks
3. **Error Handling**: Gracefully handle errors without breaking tests
4. **Measure Everything**: Add measurements for debugging and analysis
5. **Document Assumptions**: Clearly document what your hooks expect
6. **Test Your Hooks**: Write tests for your hook implementations
7. **Performance Matters**: Keep hooks fast and efficient
8. **Use Configuration**: Make hooks configurable via parameters

Common Pitfalls
---------------

❌ **Assuming hook order**: Hooks may run in any order unless specified
❌ **Not cleaning up**: Resource leaks can cause test failures
❌ **Silent failures**: Always log errors appropriately
❌ **Overusing hooks**: Not every problem needs a hook
❌ **Complex logic**: Keep hooks simple and focused
❌ **Ignoring status**: Check test status before processing results

Advanced Hook Techniques
------------------------

Conditional Hook Execution
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_setup(job):
       # Only run for specific test types
       if "performance" in job.keywords:
           setup_performance_monitoring()
       elif "integration" in job.keywords:
           setup_integration_environment()

Hook Chaining
^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl(tryfirst=True)
   def canary_runtest_setup(job):
       # Runs before other setup hooks
       initialize_base_resources()

   @hookimpl(trylast=True)
   def canary_runtest_setup(job):
       # Runs after other setup hooks
       finalize_setup()

Context Management
^^^^^^^^^^^^^^^^^^

.. code-block:: python

   @hookimpl
   def canary_runtest_setup(job):
       # Store context
       context = create_context()
       job.variables["context"] = context

   @hookimpl
   def canary_runtest_finish(job):
       # Retrieve and cleanup context
       context = job.variables.get("context")
       if context:
           cleanup_context(context)

.. seealso::

   - :doc:`/tutorial/advanced/hooks`: Complete hook system overview
   - :doc:`/extending/hooks`: All available hooks
   - :doc:`/user/workflows`: Workflow patterns
   - :doc:`/api/hooks`: Hook API reference
   - :doc:`/extensions/pyt/directives`: Python directives