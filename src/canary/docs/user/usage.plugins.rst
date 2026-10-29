.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-plugins:

Customization and metadata
==========================

A small plugin is often the easiest way to add site-specific behavior without
editing every test.  Common uses include

* recording provenance such as a git SHA,
* parsing a result file and storing structured measurements,
* setting environment variables before a job runs, and
* aggregating per-job data into session-level metadata.

This page assumes the common case: a local hook module that you load for one
run.  For packaging, entry points, and the full hook catalog, see
:doc:`/user/extending` and :doc:`/extensions/hooks`.

Loading a local hook module
---------------------------

Most users do not need to package a plugin.  Put one or more hook functions in a
small Python module and load it with the global ``-p`` option.

Hook functions are ordinary Python functions marked with
``@canary.hookimpl``:

.. code-block:: python

   import canary


   @canary.hookimpl
   def canary_runteststart(case: canary.Job) -> None:
       ...

Then load that code before the subcommand.  ``-p`` accepts three practical
forms:

* an importable module name,
* a ``.py`` file path, or
* a package directory path containing ``__init__.py``.

For example:

.. code-block:: console

   $ canary -p mysite.hooks run .
   $ canary -p ./myhooks.py run .
   $ canary -p ./myhooks_pkg run .

``-p`` is a global option, so it must appear before ``run``, ``status``, or any
other subcommand.

When to use a plugin
--------------------

Use a plugin when the behavior belongs outside the test body or should be
applied the same way across many tests.  Typical examples are:

* reading metadata from the source tree,
* recording measurements from a common output file format,
* injecting site or machine information into each job, and
* publishing a summary after the run completes.

If the logic only matters for one test, keep it in the test file.

Choosing a hook
---------------

For this kind of customization, most hook modules start with one of these:

``canary_runteststart``
  Runs once per job after the workspace is created and before the job command
  runs.  Use it to prepare inputs, set environment variables, or record
  provenance that is already known before execution.

``canary_runtest_finish``
  Runs once per job after the job command finishes.  Use it to read files from
  the job workspace, parse results, and add measurements.

``canary_sessionfinish``
  Runs once after the session completes.  Use it to aggregate results across
  jobs and attach session-level metadata.

Both ``canary_runteststart`` and ``canary_runtest_finish`` run with the current
working directory set to the job workspace.

Recording a git SHA for each job
--------------------------------

One common use is to record the version of the code under test for each job.
The example below records the SHA from the repository that contains the test
source file.

.. code-block:: python

   from pathlib import Path
   import subprocess

   import canary


   def _git_sha(path: Path) -> str | None:
       try:
           result = subprocess.run(
               ["git", "-C", str(path), "rev-parse", "HEAD"],
               check=True,
               capture_output=True,
               text=True,
           )
       except (OSError, subprocess.CalledProcessError):
           return None
       return result.stdout.strip() or None


   @canary.hookimpl
   def canary_runteststart(case: canary.Job) -> None:
       root = Path(case.spec.file).resolve().parent
       sha = _git_sha(root)
       if sha is not None:
           case.add_measurement("git_sha", sha)

This records provenance before the job runs.  The measurement is then available
through :doc:`/user/usage.query` and in reports that display job measurements.

Inspect one job's measurement:

.. code-block:: console

   $ canary query job JOB_ID measurements.git_sha

Show the measurement for every job in the latest session:

.. code-block:: console

   $ canary query session latest --expand-jobs measurements.git_sha

Adding measurements after completion
------------------------------------

``canary_runtest_finish`` is the usual place to turn output files into
structured data.  The example below reads a ``metrics.json`` file produced by
the test and stores selected values as measurements.

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

``trylast=True`` is often useful for post-processing hooks so they run after any
other finish hooks working in the same directory.

After the run, inspect the measurements directly:

.. code-block:: console

   $ canary query job JOB_ID measurements
   $ canary query jobs --session latest --where measurements.accuracy>=0.95

Because the values are stored as measurements, you can query them later without
scraping logs.

Adding environment or site metadata
-----------------------------------

Another common pattern is to capture machine or site data for each job.  For
example, this hook records the hostname and a selected environment variable:

.. code-block:: python

   import os
   import socket

   import canary


   @canary.hookimpl
   def canary_runteststart(case: canary.Job) -> None:
       case.add_measurement("hostname", socket.gethostname())
       if "CUDA_VISIBLE_DEVICES" in os.environ:
           case.add_measurement("cuda_visible_devices", os.environ["CUDA_VISIBLE_DEVICES"])

This helps when a run spans several machines or when debugging later depends on
knowing where a job ran.

Aggregating metadata for the session
------------------------------------

Use ``canary_sessionfinish`` when the value belongs to the session as a whole
rather than to one job.  The next example counts how many jobs recorded a git
SHA and stores that count in the session manifest.

.. code-block:: python

   import canary


   @canary.hookimpl
   def canary_sessionfinish(session: canary.Session) -> None:
       count = 0
       for job in session.jobs:
           if "git_sha" in job.measurements.data:
               count += 1
       session.add_measurement("jobs_with_git_sha", count)

Inspect the session-level measurement with

.. code-block:: console

   $ canary query session latest measurements.jobs_with_git_sha

Notes
-----

* A plugin loaded with ``-p``, the ``plugins`` config field, or an installed
  entry point is propagated to worker processes and nested execution contexts.
* ``canary_runtest_finish`` failures are logged for diagnosis and do not change
  the job's outcome.
* Use ``canary exec JOB_ID`` when you want to debug hook code interactively in a
  single process.

See also
--------

* :doc:`/user/extending` for plugin loading and authoring basics
* :doc:`/user/usage.query` for querying measurements and session data
* :doc:`/extensions/hooks` for the full hook reference
