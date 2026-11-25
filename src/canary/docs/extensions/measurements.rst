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

Canary's default plugins record some measurements of every job (``command_line``,
``duration``, ``inputs``, ``cpu_percent``, ...), and other plugins and hooks add their
own, all through ``add_measurement`` into one flat namespace.  The first value recorded under a name in a run is kept: recording the name again raises
``MeasurementExists`` (a ``ValueError``), unless ``replace=True`` (to update a value you
recorded yourself).  Give yours your own names (``solve_time``, not ``duration``); plugins
should prefix theirs (``myplugin::name``; ``::`` rather than ``.``, so that
``canary query job ID measurements.myplugin::name`` still works).  The default plugins
record ``duration``, ``samples``, ``inputs``, ``command_line``, ``cpu_percent``,
``memory_rss_mb``, ``memory_vms_mb`` and ``num_threads``, unprefixed.
``canary query job JOB_ID measurements`` shows what a job has.

Add measurements from hooks, which run in the process that owns the job.  Calling
``add_measurement`` inside the test process does not persist: the parent process writes the job's final record.  Have the test write
its values to a file in its working directory and record them in
``canary_runtest_finish``, as in the examples below.

Hook arguments are matched by name: the job hooks take ``case``, the session hooks
``session``.

Canary also records some measurements for every job: ``command_line``, ``duration``,
``cpu_percent``, ``memory_rss_mb``, ``memory_vms_mb``, ``num_threads``, ``samples``
(resource-usage samples taken while the job ran) and ``inputs`` (the files staged into
the job's directory).

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
   def canary_runtest_finish(case):
       case.add_measurement("max_memory", get_max_memory())
       case.add_measurement("peak_cpu", get_peak_cpu())

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

A job's and a session's measurements are under ``measurements``, by name:

.. code-block:: console

   $ canary query -s latest measurements.campaign
   "optimization-run-1"

   $ canary query -j JOB_ID measurements.max_memory
   1024

   $ canary query -j JOB_ID measurements        # every measurement of the job

   $ canary query session latest measurements.jobs_with_accuracy
   12

Across jobs, with SQL against the results table:

.. code-block:: console

   $ canary query db "SELECT spec_name, json_extract(measurements, '$.accuracy') AS accuracy
                      FROM results WHERE accuracy IS NOT NULL"

Using Measurements for Agents
-----------------------------

Agents read measurements through the Python query API (plain dicts and lists, for
the workspace in the current directory):

.. code-block:: python

   from _canary.app import query

   for row in query.measurement_table(key="accuracy"):  # latest session; session=None for all
       if row["value"] > 0.95:
           mark_as_success(row["id"])
       else:
           schedule_for_review(row["id"])

   query.measurement("JOB_ID", "loss")       # one value
   query.measurements("JOB_ID")              # every measurement of one job
   query.raw_session_value("latest", "measurements.campaign")

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
   def canary_runtest_finish(case):
       # Performance metrics
       case.add_measurement("wall_seconds", case.timekeeper.total())
       case.add_measurement("cpu_utilization", get_cpu_utilization())
       case.add_measurement("memory_usage", get_memory_usage())

**Custom Metrics**:

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_finish(case):
       # Domain-specific metrics
       if case.spec.family.startswith("ml_"):
           accuracy = parse_accuracy_from_output(case)
           loss = parse_loss_from_output(case)
           case.add_measurement("accuracy", accuracy)
           case.add_measurement("loss", loss)

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
       # command="run": canary run --track-metrics (omit for a global option,
       # given before the subcommand: canary --track-metrics run ...)
       parser.add_argument("--track-metrics", action="store_true", command="run")

   @canary.hookimpl
   def canary_runtest_finish(case):
       if canary.config.getoption("track_metrics"):
           case.add_measurement("custom_metric", calculate_metric())

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
   def canary_runtest_finish(case):
       case.add_measurement("test_result", parse_result_file("result.json"))

   # Bad: Log scraping
   @canary.hookimpl
   def canary_runtest_finish(case):
       with open(case.workspace.joinpath(case.stdout)) as f:
           for line in f:
               if "RESULT:" in line:
                   # Parse from log
                   pass

Measurement Troubleshooting
---------------------------

**Measurements Not Found**:

.. code-block:: console

   $ canary query -j JOB_ID measurements.loss
   ERROR: "No such key: 'loss'. Available keys: command_line, cpu_percent, ..."

- Is the hook module loaded (``canaryhooks.py`` in the directory ``canary`` runs from,
  or ``canary -p MODULE run ...``)?  The session log says ``Using hooks from FILE`` for
  each one.
- Does the hook take an argument named ``case`` (or ``session``)?
- Was the measurement added in a hook rather than inside the test process?
- Was the run started with the ``canary run`` command?  The in-process
  ``_canary.app.run_request.run`` does not load ``canaryhooks.py``.
- Inspect one job directly with ``canary query job JOB_ID measurements``.

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
