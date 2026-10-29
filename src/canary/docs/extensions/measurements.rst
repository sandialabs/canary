.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-measurements:

Measurements
============

Measurements are structured values attached to jobs or sessions.  They are
persisted with the run state, exposed through ``canary query``, and available to
reporters and later automation.

Use the user guide page :doc:`/user/usage.plugins` for examples such as
recording git SHAs or parsing a metrics file.  This page describes the
measurement API and where it fits in the run lifecycle.

Data model
----------

Two public APIs are used to attach measurements:

``case.add_measurement(name, value)``
  Adds or updates a job-level measurement.

``session.add_measurement(name, value)``
  Adds or updates a session-level measurement.

Values should be JSON-serializable.  Scalars are common, but lists and mapping
values are also fine when a measurement naturally has structure.

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

Measurements can be added at several points in the lifecycle:

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
   def canary_runteststart(case):
       # Pre-execution measurements (before the job command runs)
       case.add_measurement("initial_resources", get_resources())

   @canary.hookimpl(trylast=True)
   def canary_runtest_finish(case):
       # Post-execution measurements
       case.add_measurement("final_resources", get_resources())

In practice:

``canary_runteststart``
  Use for provenance or environment facts that are already known before the job
  command runs.

``canary_runtest_finish``
  Use for post-processing files created by the job and turning them into
  structured measurements.

``canary_sessionfinish``
  Use for values aggregated across many jobs.

Both ``canary_runteststart`` and ``canary_runtest_finish`` run with the current
working directory set to the job workspace.

Example: per-job post-processing
--------------------------------

The most common measurement hook is ``canary_runtest_finish``.  The example
below reads a ``metrics.json`` file produced by the job and stores selected
values as measurements.

.. code-block:: python

   import json
   from pathlib import Path

   import canary


   @canary.hookimpl(trylast=True)
   def canary_runtest_finish(case: canary.Job) -> None:
       metrics_file = Path("metrics.json")
       if not metrics_file.exists():
           return

       data = json.loads(metrics_file.read_text())
       if "throughput" in data:
           case.add_measurement("throughput", data["throughput"])
       if "accuracy" in data:
           case.add_measurement("accuracy", data["accuracy"])

``trylast=True`` is often appropriate when a finish hook depends on files or
state produced by other finish hooks.

Example: session aggregation
----------------------------

Session-level measurements are useful for rollups that do not belong to a
single job:

.. code-block:: python

   import canary


   @canary.hookimpl
   def canary_sessionfinish(session: canary.Session) -> None:
       n = 0
       for job in session.jobs:
           if "accuracy" in job.measurements.data:
               n += 1
       session.add_measurement("jobs_with_accuracy", n)

Querying Measurements
---------------------

Query measurements with ``canary query``:

.. code-block:: console

   $ canary query -s latest measurements.campaign
   "optimization-run-1"

   $ canary query -j JOB_ID measurements.max_memory
   1024

   $ canary query session latest measurements.jobs_with_accuracy
   12

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
- Store structured data instead of encoding many values into one string
- Prefer reading machine-written result files over scraping human-oriented logs

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

When a test already writes a structured result file, read that file directly and
store the values as measurements.  Avoid parsing ad hoc text output when a more
stable source exists.

**Prefer structured measurements**:

.. code-block:: python

   # Good: Structured measurement
   @canary.hookimpl
    def canary_runtest_finish(job):
        job.add_measurement("test_result", parse_result_file("result.json"))

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
- Inspect one job directly with ``canary query job JOB_ID measurements``

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
- :doc:`/user/commands/query`: Querying measurements
