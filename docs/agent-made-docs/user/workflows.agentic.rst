.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-workflows-agentic:

Agentic Workflows
=================

An agent drives Canary the same way a person does: it runs a session, reads the
results, decides what to do next, and runs again.  Canary keeps every session and
result in the workspace (``.canary/``), so an agent can stop and resume, compare
sessions, and read structured data instead of scraping logs.

Two interfaces matter:

* The ``canary`` command line for running (``canary run``) and for reading
  (``canary status --json``, ``canary query ...``).  Output is JSON.
* The Python read API in ``_canary.api`` (``status``, ``query``) for agents written
  in Python.

The agent loop
--------------

1. **Run.**  ``canary run PATH`` creates the workspace on first use and runs every
   job found under ``PATH``.  The exit code is 0 when everything passed.

   .. code-block:: console

      $ canary run tests
      $ echo $?
      8

2. **Read the outcome.**  ``canary status --json`` lists the jobs that did not
   pass (``--all`` lists every job):

   .. code-block:: console

      $ canary status --json
      [
        {
          "id": "f2ca362",
          "name": "bad",
          "session": "2026-11-18T11-49-30.278324",
          "exit_code": 1,
          "status": {"category": "FAIL", "outcome": "FAILED",
                     "reason": "Test exited with exit code = 1"},
          ...
        }
      ]

3. **Read structured data.**  Job measurements live under ``measurements.data``;
   session measurements directly under ``measurements``:

   .. code-block:: console

      $ canary query -j 2b46fb8 measurements.data.loss
      0.02
      $ canary query -s latest measurements.campaign
      "demo-1"

4. **Decide and run again.**  Rerun what failed, one job by ID, or a filtered
   subset:

   .. code-block:: console

      $ canary run --only failed tests     # only jobs that failed last time
      $ canary run f2ca362                 # one job (defaults to --only all)
      $ canary run -k regression tests     # jobs with the "regression" keyword

``canary run PATH`` defaults to ``--only not_pass``: jobs that already passed are not
rerun.  Use ``--only all`` to rerun everything.

Recording measurements
----------------------

Measurements are recorded by hooks, which run in the process that owns the job.
Put them in a ``canaryhooks.py`` next to where you run Canary; ``canary run``
loads it automatically.  A test writes its results to a file in its working
directory, and a ``canary_runtest_finish`` hook turns them into measurements:

.. code-block:: python

   # tests/opt.pyt
   import json
   import sys

   import canary

   canary.directives.keywords("regression")
   canary.directives.parameterize("lr", (0.1, 0.01))


   def test():
       lr = canary.get_instance().parameters.lr
       with open("result.json", "w") as fh:
           json.dump({"loss": lr * 2}, fh)
       return 0


   if __name__ == "__main__":
       sys.exit(test())

.. code-block:: python

   # canaryhooks.py
   import json

   import canary


   @canary.hookimpl
   def canary_runtest_finish(case):
       result = case.workspace.joinpath("result.json")
       if result.exists():
           case.add_measurement("loss", json.loads(result.read_text())["loss"])


   @canary.hookimpl
   def canary_sessionstart(session):
       session.add_measurement("campaign", "demo-1")


   @canary.hookimpl
   def canary_sessionfinish(session):
       session.add_measurement("job_count", len(session.jobs))

The hook argument is named ``case`` (a :class:`~_canary.core.job.Job`); pluggy
matches hook arguments by name.  Calling ``add_measurement`` from inside the test
process does not persist: the parent's record of the job replaces it.

Reading results from Python
---------------------------

``_canary.api.status`` and ``_canary.api.query`` return plain dicts and lists, read
from the workspace in the current directory:

.. code-block:: python

   from _canary.api import query, status

   status.ok()                        # True if nothing failed
   status.summary()                   # {"total": 3, "passed": 2, "failed": 1, ...}
   [e["name"] for e in status.failed()]               # ["bad"]

   query.measurement_table(key="loss")
   # [{"id": "2b46fb8", "name": "opt.lr=0.01", "key": "loss", "value": 0.02, ...}, ...]
   query.measurement("2b46fb8", "loss")                # 0.02
   query.raw_session_value("latest", "measurements.campaign")   # "demo-1"
   query.job_history("f2ca362")       # one entry per run of that job

``query.measurement_table`` reads the latest session by default; pass
``session=None`` for the latest run of each job across all sessions.

``_canary.api.run.run("tests")`` starts a run in-process.  It does **not** load
``canaryhooks.py``, so measurement hooks do not fire; run through the
``canary run`` command when you rely on hooks.  On Python 3.14 the worker pool
re-imports the main module, so a script that calls ``run`` needs an
``if __name__ == "__main__":`` guard.

Querying the workspace
----------------------

.. code-block:: console

   $ canary query jobs --where "status.category==FAIL" --digest
   bad FAIL
   $ canary query sessions                      # one entry per session, with counts
   $ canary query compare BASE_SESSION NEW_SESSION --digest
   bad FAILED->FAILED
   $ canary query failures --session latest     # failures grouped by log signature
   $ canary query db "SELECT spec_name, json_extract(measurements, '$.data.loss') AS loss
                      FROM results WHERE loss IS NOT NULL"

``canary query -j JOB --list`` and ``canary query -s SESSION --list`` show the keys
available at a path.

Example: an optimization loop
-----------------------------

The agent runs the parameterized test through the CLI (so the measurement hook
fires) and reads the measurements through the Python API:

.. code-block:: python

   import subprocess

   from _canary.api import query


   def best_loss() -> tuple[str, float]:
       rows = query.measurement_table(key="loss")
       best = min(rows, key=lambda row: row["value"])
       return best["name"], best["value"]


   def main(max_iterations: int = 5) -> None:
       for iteration in range(max_iterations):
           subprocess.run(["canary", "run", "--only", "all", "tests"], check=False)
           name, loss = best_loss()
           print(f"iteration {iteration}: best {name} loss={loss}")
           if loss < 0.05:
               break
           update_parameters(name)  # your logic: edit inputs for the next run


   if __name__ == "__main__":
       main()

For CI, ``canary run`` exits non-zero when any job fails, and ``canary report
junit`` (or ``json``, ``markdown``, ``html``) writes a report from the latest
results.

Agent safety guidance
---------------------

* **Do not edit lock files** (``testcase.lock``, ``session.lock``) or the database.
  Canary owns them; record data through measurements.
* **Prefer structured data.**  Record values with ``add_measurement`` in a hook and
  read them with ``canary query``; scrape logs only when nothing structured exists.
* **Bound each run.**  Name explicit paths, IDs, keywords (``-k``) or parameters
  (``-p``), and choose ``--only`` deliberately.
* **Keep provenance.**  Session measurements (``canary_sessionstart``) record why a
  run happened; ``canary query sessions`` keeps every session's argv and counts.

Troubleshooting
---------------

**A measurement is missing**:

.. code-block:: console

   $ canary query -j 2b46fb8 measurements.data.loss
   ERROR: "No such key: 'loss'. Available keys: command_line, cpu_percent, ..."

Check that ``canaryhooks.py`` is in the directory you run ``canary`` from, that the
hook takes an argument named ``case``, and that the run went through ``canary run``
(not the in-process Python ``run``).

**Nothing reran**: ``canary run PATH`` skips jobs that already passed
(``--only not_pass``).  Use ``--only all``.

See Also
--------

- :doc:`concepts`: Core architectural concepts
- :doc:`workspaces`: Workspace structure and management
- :doc:`query`: Advanced querying capabilities
- :doc:`workflows`: Common workflow patterns
- :doc:`/reference/commands.query`: Query command reference
- :doc:`/reference/commands.config`: Config command reference
