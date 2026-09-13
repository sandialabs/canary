.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-debugging:

Debugging test failures
=======================

``canary`` provides a set of complementary tools for inspecting execution state,
diagnosing failures, and understanding what happened inside a test run.  This page
collects them into a coherent debugging workflow.

Inspecting overall status
--------------------------

Start with ``canary status`` to see what happened across the session:

.. code-block:: console

   $ canary status
   ID      Name            Session   Exit Code  Duration  Status
   a1b2c3  test1.pyt       sess-1    0           42.50     passed
   d4e5f6  test2.pyt       sess-1    1           120.25    failed

Filter by outcome to reduce noise:

.. code-block:: console

   $ canary status -rf    # failed only
   $ canary status -rt    # timed-out only
   $ canary status -ra    # all non-passing statuses

Show the slowest tests:

.. code-block:: console

   $ canary status --durations=10

Inspecting logs
---------------

View a job's stdout with ``canary log``:

.. code-block:: console

   $ canary log JOB_ID

View stderr instead:

.. code-block:: console

   $ canary log --error JOB_ID

View the job's ``testcase.lock`` (structured JSON state):

.. code-block:: console

   $ canary log --lock JOB_ID

View any other file in the job's execution directory by name:

.. code-block:: console

   $ canary log --file canary-out.txt JOB_ID

Locating execution directories
-------------------------------

Find a job's execution directory:

.. code-block:: console

   $ cd $(canary location JOB_ID)

Locate the job's input (source) file:

.. code-block:: console

   $ canary location -i JOB_ID

Locate the job's log file:

.. code-block:: console

   $ canary location -l JOB_ID

Locate the job's source directory:

.. code-block:: console

   $ canary location -s JOB_ID

Once inside the execution directory, examine the files directly:

.. code-block:: console

   $ ls -la
   $ cat canary-out.txt
   $ cat canary-err.txt

Querying structured state
--------------------------

``canary query`` reads ``testcase.lock`` and ``session.lock`` files and returns
values at arbitrary dot-notation paths:

.. code-block:: console

   $ canary query job JOB_ID .status
   {
     "category": "FAIL",
     "outcome": "FAILED",
     "reason": "AssertionError: expected 42, got 24",
     "code": 1
   }

   $ canary query job JOB_ID .status.reason
   "AssertionError: expected 42, got 24"

   $ canary query job JOB_ID .measurements
   {"duration": 42.5, "memory_usage": 1024}

Query session-level data:

.. code-block:: console

   $ canary query session SESSION_ID .jobs
   ["JOB_1", "JOB_2", "JOB_3"]

Step-by-step failure workflow
-------------------------------

1. Identify failing jobs:

   .. code-block:: console

      $ canary status -rf

2. Inspect the failure reason:

   .. code-block:: console

      $ canary query job JOB_ID .status.reason

3. View the full execution log:

   .. code-block:: console

      $ canary log JOB_ID

4. Navigate to the execution directory:

   .. code-block:: console

      $ cd $(canary location JOB_ID)

5. Examine workspace files and artifacts:

   .. code-block:: console

      $ ls -la
      $ cat canary-out.txt

Debugging blocked dependencies
--------------------------------

When a job is ``blocked`` because a dependency failed:

.. code-block:: console

   $ canary describe BLOCKED_JOB_ID
   blocked_job.pyt
   └── dependency.pyt (FAILED)

Check the dependency's status and log:

.. code-block:: console

   $ canary status dependency.pyt
   $ canary log DEPENDENCY_JOB_ID

Rerun the dependency once fixed:

.. code-block:: console

   $ canary run dependency.pyt

Debugging resource-capacity failures
--------------------------------------

When a test is skipped or blocked due to insufficient resources:

.. code-block:: console

   Error: insufficient slots on node hostname of cpus (requested 16, available 8)

Solutions:

- Reduce the test's CPU/GPU parameter
- Increase the resource pool: ``canary -r cpus=32 run .``
- Check current pool capacity: ``canary config show resource-pool``

Debugging timeouts
------------------

.. code-block:: console

   $ canary status -rt
   ID      Name            Duration  Status   Details
   a1b2c3  slow_test.pyt   600.50    timeout  Exceeded 600s limit

Increase the timeout in configuration:

.. code-block:: yaml

   canary:
     run:
       timeout:
         long: 1800.0

Or override on a single run:

.. code-block:: console

   $ canary run --timeout default=1800s slow_test.pyt

Debugging interrupted or cancelled sessions
-------------------------------------------

If a session was interrupted (e.g., by Ctrl-C), jobs that did not run will have a
``cancelled`` or ``blocked`` status.  Rerun only what was not executed:

.. code-block:: console

   $ canary run --only=not_run .

To resume a specific session:

.. code-block:: console

   $ canary run --session=SESSION_NAME .

Debugging stale views
---------------------

If ``TestResults/`` is out of sync with the database:

.. code-block:: console

   $ canary view --rebuild

Check the current view configuration:

.. code-block:: console

   $ canary config show workspace.view

Enabling debug logging
----------------------

.. code-block:: console

   $ canary -d run my_test.pyt        # debug mode
   $ canary --verbose run my_test.pyt # verbose logging

Or permanently in configuration:

.. code-block:: yaml

   canary:
     debug: true
     log_level: DEBUG

Rerun strategies for debugging
--------------------------------

.. code-block:: console

   $ canary run --only=failed .        # only failed jobs
   $ canary run --only=not_run .       # only jobs that never ran
   $ canary run --workers=1 .          # single-threaded; eliminates concurrency issues
   $ canary run -r cpus=8 .            # explicit resource pool

Advanced techniques
-------------------

**Inspect the dependency graph**:

.. code-block:: console

   $ canary describe JOB_ID

**Check resource allocations**:

.. code-block:: console

   $ canary query job JOB_ID .resources

Debugging checklist
-------------------

1. Check overall status: ``canary status``
2. Inspect job logs: ``canary log JOB_ID``
3. Query structured state: ``canary query job JOB_ID .status``
4. Locate execution directory: ``canary location JOB_ID``
5. Verify resource pool: ``canary config show resource-pool``
6. Check dependencies: ``canary describe JOB_ID``
7. Review configuration: ``canary config show``
8. Enable debug logging if needed: ``canary -d run``
9. Rerun with appropriate ``--only`` strategy

See Also
--------

- :ref:`basics-status` — status values and their meanings
- :ref:`usage-run-basic` — run options and flags
- :ref:`usage-rerun` — rerun strategies
- :ref:`user-dependencies` — dependency model and troubleshooting
