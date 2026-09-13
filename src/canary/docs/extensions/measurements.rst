.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-measurements:

Measurements
============

Measurements provide structured data collection for analysis and automation. Extensions can add custom measurements at various lifecycle points.

Adding Measurements
-------------------

**Session.add_measurement**: Add session-level measurements

.. code-block:: python

   @canary.hookimpl
   def canary_sessionstart(session):
       session.add_measurement("campaign", "optimization-run-1")
       session.add_measurement("objective", "minimize_loss")

**Job.add_measurement**: Add job-level measurements

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_finish(job):
       job.add_measurement("max_memory", get_max_memory())
       job.add_measurement("peak_cpu", get_peak_cpu())

Measurement Hooks
-----------------

Add measurements in lifecycle hooks:

.. code-block:: python

   @canary.hookimpl
   def canary_sessionstart(session):
       # Session startup measurements
       session.add_measurement("start_time", time.time())

   @canary.hookimpl
   def canary_sessionfinish(session):
       # Session completion measurements
       session.add_measurement("duration", calculate_duration())

   @canary.hookimpl
   def canary_runtest_setup(job):
       # Pre-execution measurements
       job.add_measurement("initial_resources", get_resources())

   @canary.hookimpl
   def canary_runtest_finish(job):
       # Post-execution measurements
       job.add_measurement("final_resources", get_resources())

Querying Measurements
---------------------

Query measurements with ``canary query``:

.. code-block:: console

   $ canary query -s latest measurements.campaign
   "optimization-run-1"

   $ canary query -j JOB_ID measurements.max_memory
   1024

   $ canary query -j JOB_ID measurements.data.peak_cpu
   85.5

Using Measurements for Agents
-----------------------------

Agents use measurements for decision making:

.. code-block:: python

   def agent_decision_loop():
       workspace = canary.Workspace.load()
       results = workspace.db.get_results()

       for job_id, result in results.items():
           measurements = result["measurements"]

           if measurements.get("accuracy", 0) > 0.95:
               mark_as_success(job_id)
           elif measurements.get("loss", float('inf')) < 0.05:
               schedule_for_review(job_id)
           else:
               rerun_with_different_params(job_id)

Measurement Best Practices
--------------------------

**Structured Data**:

- Use meaningful measurement names
- Store structured data (not just strings)
- Avoid log scraping patterns

**Performance**:

- Minimize measurement overhead
- Cache expensive measurements
- Sample where appropriate

**Consistency**:

- Use consistent naming conventions
- Document measurement semantics
- Provide units where applicable

Measurement Examples
--------------------

**Performance Monitoring**:

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_finish(job):
       # Performance metrics
       job.add_measurement("duration", job.timekeeper.duration())
       job.add_measurement("cpu_utilization", get_cpu_utilization())
       job.add_measurement("memory_usage", get_memory_usage())

**Custom Metrics**:

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_finish(job):
       # Domain-specific metrics
       if job.spec.name.startswith("ml_"):
           accuracy = parse_accuracy_from_output(job)
           loss = parse_loss_from_output(job)
           job.add_measurement("accuracy", accuracy)
           job.add_measurement("loss", loss)

**Resource Tracking**:

.. code-block:: python

   @canary.hookimpl
   def canary_sessionfinish(session):
       # Aggregate resource usage
       total_cpu_hours = calculate_total_cpu_hours(session)
       total_memory_gb = calculate_total_memory_gb(session)
       session.add_measurement("total_cpu_hours", total_cpu_hours)
       session.add_measurement("total_memory_gb", total_memory_gb)

Measurement Integration
-----------------------

**Configuration Integration**:

.. code-block:: python

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument("--track-metrics", action="store_true")

   @canary.hookimpl
   def canary_runtest_finish(job):
       if canary.config.getoption("track_metrics"):
           job.add_measurement("custom_metric", calculate_metric())

**Environment Integration**:

.. code-block:: python

   @canary.hookimpl
   def canary_sessionstart(session):
       # Record environment information
       session.add_measurement("hostname", socket.gethostname())
       session.add_measurement("python_version", sys.version)

Avoiding Log Scraping
---------------------

**Prefer structured measurements**:

.. code-block:: python

   # Good: Structured measurement
   @canary.hookimpl
   def canary_runtest_finish(job):
       job.add_measurement("test_result", parse_result(job.stdout))

   # Bad: Log scraping
   @canary.hookimpl
   def canary_runtest_finish(job):
       with open(job.stdout) as f:
           for line in f:
               if "RESULT:" in line:
                   # Parse from log
                   pass

Measurement Troubleshooting
---------------------------

**Measurements Not Found**:

- Verify measurement addition timing
- Check hook execution order
- Ensure proper measurement names

**Query Failures**:

- Validate measurement paths
- Check measurement existence
- Test query syntax

**Performance Issues**:

- Profile measurement collection
- Optimize expensive calculations
- Consider sampling strategies

See Also
--------

- :doc:`plugins`: Measurement plugin registration
- :doc:`hooks`: Measurement-related hooks
- :doc:`/user/workflows.agentic`: Agent workflows using measurements
- :doc:`../user/query`: Querying measurements