.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-session:

Sessions
========

A **session** represents a single execution run of ``canary`` jobs.  It coordinates
job execution, manages runtime state, and tracks results within a
:ref:`workspace <basics-workspace>`.

What a session is
-----------------

A ``canary`` session is:

- A coordinated execution of one or more jobs
- A runtime context with shared configuration and resources
- A container for job results and measurements
- An atomic unit of work for reporting and analysis

Sessions are created within workspaces and manage the complete execution lifecycle
from job dispatch through result persistence.  Each ``canary run`` invocation creates
a new session.

Session directory layout
------------------------

Sessions are stored in the workspace ``sessions/`` directory:

.. code-block:: text

   .canary/
   └── sessions/
       └── {session_name}/
           ├── session.lock        # Session manifest
           ├── job1_dir/           # Job execution directories
           │   ├── testcase.lock   # Job state
           │   ├── canary-out.txt  # stdout
           │   └── artifacts/      # Output files
           ├── job2_dir/
           │   └── ...
           └── ...

Session names are ISO-format timestamps by default
(e.g., ``2024-01-15T12-34-56.789012``), ensuring uniqueness and providing a
human-readable creation time.

session.lock
------------

The ``session.lock`` file is the session manifest written at the end of each run.
It records:

.. code-block:: json

   {
     "name": "2024-01-15T12-34-56.789012",
     "prefix": ".canary/sessions/2024-01-15T12-34-56.789012",
     "job_ids": ["job_id_1", "job_id_2", "job_id_3"],
     "returncode": 0,
     "started_on": "2024-01-15T12:34:56.789012",
     "finished_on": "2024-01-15T12:35:12.345678",
     "argv": ["canary", "run", "."],
     "config": {"canary": {"...": "..."}},
     "measurements": {
       "total_jobs": 42,
       "successful": 40,
       "failed": 2,
       "runtime": 345.678
     }
   }

This file is written by ``canary`` and should not be edited manually.

Latest session reference
------------------------

The most recently completed session is referenced by ``.canary/refs/latest``:

.. code-block:: text

   ../sessions/2024-01-15T12-34-56.789012

This relative symlink is updated automatically after every run.  Commands such as
``canary status`` and ``canary log`` use it when no specific session is requested.

Session lifecycle
-----------------

Sessions progress through a well-defined sequence:

1. **Creation** — session object instantiated with the resolved job list
2. **Initialization** — workspace directory prepared; jobs validated
3. **Hook invocation** — ``canary_sessionstart`` hooks called
4. **Execution** — jobs dispatched, monitored, and managed
5. **Result collection** — job status and measurements gathered
6. **Database update** — results persisted to ``workspace.sqlite3``
7. **View update** — ``TestResults/`` view refreshed
8. **Hook invocation** — ``canary_sessionfinish`` hooks called
9. **Completion** — ``session.lock`` written

Session return codes
--------------------

Sessions report overall status through their return code:

- **0** — all jobs completed successfully
- **1** — one or more jobs failed
- **2** — configuration or setup error
- **3** — resource allocation failure
- **4** — dependency resolution failure
- **7** — session timeout
- **other** — specific codes from plugins or extensions

The return code is stored in ``session.lock`` and is also the process exit code of
``canary run``.

Rerun strategies
----------------

When re-running tests, the ``--only`` option controls which jobs from a previous
session are included:

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Strategy
     - Behaviour
   * - ``not_pass`` *(default)*
     - Run jobs that did not pass in the previous session
   * - ``all``
     - Run all jobs regardless of previous status
   * - ``failed``
     - Run only jobs that failed previously
   * - ``not_run``
     - Run only jobs that were not executed previously

See :ref:`usage-rerun` for rerun examples.

Session management commands
---------------------------

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Command
     - Purpose
   * - ``canary run``
     - Execute jobs in a new session
   * - ``canary status``
     - Query session and job status
   * - ``canary info``
     - Show workspace and session information
   * - ``canary gc``
     - Clean up old session directories to reclaim disk space
   * - ``canary report``
     - Generate reports from session results

Session hooks
-------------

Plugins can participate in the session lifecycle through hooks:

- **canary_sessionstart** — called when session execution begins
- **canary_sessionfinish** — called when session execution completes

These hooks can initialize resources, monitor progress, collect session-level
measurements, generate custom reports, or clean up after execution.

Session isolation
-----------------

Each session has a dedicated subdirectory under ``.canary/sessions/``, ensuring that
concurrent or sequential sessions do not interfere with one another.  The resource
pool and database transactions also enforce isolation at the runtime and storage
levels.

Session troubleshooting
-----------------------

.. list-table::
   :widths: 35 65
   :header-rows: 1

   * - Issue
     - Resolution
   * - Session fails to start
     - Check workspace configuration and job validity
   * - Jobs stuck in ``pending``
     - Verify resource availability and check for unresolved dependencies
   * - Database locked errors
     - Ensure no other ``canary`` process is accessing the workspace
   * - ``TestResults/`` view not updated
     - Check that the session completed normally; re-run with ``canary view --rebuild``
   * - Unexpected high return code
     - Inspect ``session.lock`` and individual job logs with ``canary log``
   * - Missing results after crash
     - Jobs with written ``testcase.lock`` files were recorded; re-run with ``--only not_run``
