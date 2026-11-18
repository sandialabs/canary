.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-measurements:

Measurements
============

Measurements are structured ``name -> value`` data attached to a job or a session.
They are stored with the results, so agents, reports and later sessions can read
them without scraping logs.

Adding Measurements
-------------------

Measurements are added from hooks, which run in the process that owns the job.
Put the hooks in a ``canaryhooks.py`` next to where you run Canary (``canary run``
loads it automatically), or in a plugin.

**Job measurements**: ``case.add_measurement(name, value)``, usually in
``canary_runtest_finish``.  The hook runs in the job's working directory, after the
test has run:

.. code-block:: python

   import json

   import canary


   @canary.hookimpl
   def canary_runtest_finish(case):
       result = case.workspace.joinpath("result.json")
       if result.exists():
           case.add_measurement("loss", json.loads(result.read_text())["loss"])

**Session measurements**: ``session.add_measurement(name, value)`` in
``canary_sessionstart`` or ``canary_sessionfinish``:

.. code-block:: python

   @canary.hookimpl
   def canary_sessionstart(session):
       session.add_measurement("campaign", "optimization-run-1")


   @canary.hookimpl
   def canary_sessionfinish(session):
       session.add_measurement("job_count", len(session.jobs))

Hook arguments are matched by name: the job hooks take ``case``, the session hooks
``session``.

Calling ``add_measurement`` inside the test process (for example on
``canary.get_job()``) does not persist; the parent process writes the job's final
record.  Have the test write its values to a file in its working directory, as
above, and record them in ``canary_runtest_finish``.

Built-in Measurements
---------------------

Canary records some measurements for every job: ``command_line``, ``duration``,
``cpu_percent``, ``memory_rss_mb``, ``memory_vms_mb``, ``num_threads``,
``samples`` (resource-usage samples taken while the job ran) and ``inputs`` (the
files staged into the job's directory).

Querying Measurements
---------------------

Job measurements live under ``measurements.data``; session measurements directly
under ``measurements``:

.. code-block:: console

   $ canary query -j JOBID measurements.data.loss
   0.02
   $ canary query -j JOBID measurements.data             # every measurement of the job
   $ canary query -s latest measurements.campaign
   "optimization-run-1"

Across jobs, with SQL against the results table:

.. code-block:: console

   $ canary query db "SELECT spec_name, json_extract(measurements, '$.data.loss') AS loss
                      FROM results WHERE loss IS NOT NULL"

From Python:

.. code-block:: python

   from _canary.api import query

   query.measurement_table(key="loss")   # one row per job: id, name, session, key, value, status
   query.measurement("JOBID", "loss")
   query.measurements("JOBID")           # every measurement of one job
   query.raw_session_value("latest", "measurements.campaign")

``measurement_table`` reads the latest session; pass ``session=None`` for the latest
run of each job across all sessions.

Examples
--------

**Timing and status**:

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_finish(case):
       case.add_measurement("wall_seconds", case.timekeeper.total())
       case.add_measurement("outcome", case.status.outcome.name)

**Domain metrics from an output file**:

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_finish(case):
       if case.spec.family != "solver":
           return
       summary = case.workspace.joinpath("summary.json")
       if summary.exists():
           data = json.loads(summary.read_text())
           case.add_measurement("iterations", data["iterations"])
           case.add_measurement("residual", data["residual"])

**Option-gated metrics**:

.. code-block:: python

   @canary.hookimpl
   def canary_addoption(parser):
       parser.add_argument(
           "--track-metrics",
           dest="track_metrics",
           action="store_true",
           command="run",  # canary run --track-metrics; omit for a global option
           group="metrics",
           help="Record extra per-job metrics",
       )


   @canary.hookimpl
   def canary_runtest_finish(case):
       if canary.config.getoption("track_metrics"):
           case.add_measurement("parameters", dict(case.spec.parameters))

**Environment provenance**:

.. code-block:: python

   import socket
   import sys


   @canary.hookimpl
   def canary_sessionstart(session):
       session.add_measurement("hostname", socket.gethostname())
       session.add_measurement("python_version", sys.version.split()[0])

Avoiding Log Scraping
---------------------

Emit values in a machine-readable file (or as structured measurements) rather than
searching the job's log for them later:

.. code-block:: python

   # Good: the test writes summary.json; the hook records the values
   case.add_measurement("residual", json.loads(case.workspace.joinpath("summary.json").read_text())["residual"])

   # Fragile: parsing values out of the log
   for line in case.workspace.joinpath(case.stdout).read_text().splitlines():
       if line.startswith("RESIDUAL:"):
           ...

Measurement Troubleshooting
---------------------------

.. code-block:: console

   $ canary query -j JOBID measurements.data.loss
   ERROR: "No such key: 'loss'. Available keys: command_line, cpu_percent, ..."

* Is ``canaryhooks.py`` in the directory ``canary`` runs from (or the plugin loaded
  with ``canary -p MODULE run ...``)?
* Does the hook take an argument named ``case`` (or ``session``)?
* Was the measurement added in a hook rather than inside the test process?
* Was the run started with the ``canary run`` command?  The in-process
  ``_canary.api.run.run`` does not load ``canaryhooks.py``.
* Session measurements have no ``data`` level: ``measurements.NAME``, not
  ``measurements.data.NAME``.

See Also
--------

- :doc:`plugins`: Measurement plugin registration
- :doc:`hooks`: Measurement-related hooks
- :doc:`/user/workflows.agentic`: Agent workflows using measurements
- :doc:`../user/query`: Querying measurements
