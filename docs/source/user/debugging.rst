.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-debugging:

Debugging
=========

Canary provides comprehensive debugging tools for inspecting test execution, diagnosing failures, and understanding system state. This guide covers debugging workflows and best practices.

Inspecting Status
-----------------

Use ``canary status`` to view test execution results:

.. code-block:: console

   $ canary status
   ID      Name                Session      Exit Code  Duration  Status    Details
   a1b2c3  test1.pyt           session1     0           42.50     PASSED
   d4e5f6  test2.pyt           session1     1           120.25    FAILED    Assertion failed

Filter by status:

.. code-block:: console

   $ canary status -rf  # Show only failed tests
   $ canary status -rt  # Show only timed out tests
   $ canary status -ra  # Show all non-passed tests

Show slowest durations:

.. code-block:: console

   $ canary status --durations=10

Inspecting Logs
---------------

View test output logs with ``canary log``:

.. code-block:: console

   $ canary log JOB_ID
   [2024-01-01T12:00:00] INFO: Test starting
   [2024-01-01T12:00:05] ERROR: Assertion failed
   [2024-01-01T12:00:10] INFO: Test completed

View stderr:

.. code-block:: console

   $ canary log --error JOB_ID

View lockfile:

.. code-block:: console

   $ canary log --lock JOB_ID

View specific workspace files:

.. code-block:: console

   $ canary log --file canary-out.txt JOB_ID

Locating Execution Directories
------------------------------

Find test locations with ``canary location``:

.. code-block:: console

   $ canary location JOB_ID
   /path/to/workspace/sessions/session1/jobs/JOB_ID

Locate input files:

.. code-block:: console

   $ canary location -i JOB_ID
   /path/to/test_file.pyt

Locate log files:

.. code-block:: console

   $ canary location -l JOB_ID
   /path/to/workspace/sessions/session1/jobs/JOB_ID/canary-out.txt

Locate source directories:

.. code-block:: console

   $ canary location -s JOB_ID
   /path/to/test_directory

Reading Lock Files
------------------

Lock files contain structured execution data:

**testcase.lock**:

.. code-block:: json

   {
     "id": "JOB_ID",
     "spec": {
       "name": "test_name",
       "file": "/path/to/test.pyt",
       "parameters": {"cpus": 4, "gpus": 2}
     },
     "status": {
       "category": "FAIL",
       "outcome": "FAILED",
       "reason": "AssertionError: expected 42, got 24",
       "code": 1
     },
     "timekeeper": {
       "_started": 1234567890.0,
       "_finished": 1234567932.5
     },
     "measurements": {
       "duration": 42.5,
       "memory_usage": 1024
     }
   }

**session.lock**:

.. code-block:: json

   {
     "session": "session1",
     "started_on": "2024-01-01T12:00:00",
     "finished_on": "2024-01-01T12:05:00",
     "jobs": ["JOB_1", "JOB_2", "JOB_3"],
     "status": {
       "total": 3,
       "passed": 2,
       "failed": 1
     }
   }

Querying Structured State
--------------------------

Use ``canary query`` for detailed inspection:

.. code-block:: console

   $ canary query -j JOB_ID .status
   {
     "category": "FAIL",
     "outcome": "FAILED",
     "reason": "AssertionError: expected 42, got 24",
     "code": 1
   }

Query specific fields:

.. code-block:: console

   $ canary query -j JOB_ID .status.reason
   "AssertionError: expected 42, got 24"

Query session data:

.. code-block:: console

   $ canary query -s SESSION_ID .jobs
   ["JOB_1", "JOB_2", "JOB_3"]

Debugging Failed Jobs
---------------------

**Step-by-step debugging workflow**:

1. Identify failed jobs:

   .. code-block:: console

      $ canary status -rf

2. Inspect failure details:

   .. code-block:: console

      $ canary query -j JOB_ID .status.reason

3. View execution logs:

   .. code-block:: console

      $ canary log JOB_ID

4. Locate execution directory:

   .. code-block:: console

      $ cd $(canary location JOB_ID)

5. Examine workspace files:

   .. code-block:: console

      $ ls -la
      $ cat canary-out.txt
      $ cat canary-err.txt

Debugging Blocked Dependencies
------------------------------

When jobs are blocked by dependencies:

.. code-block:: console

   $ canary describe BLOCKED_JOB_ID
   blocked_job.pyt
   └── dependency.pyt (FAILED)

Check dependency status:

.. code-block:: console

   $ canary status dependency.pyt
   $ canary log dependency.pyt

Rerun dependencies:

.. code-block:: console

   $ canary run dependency.pyt

Debugging Resource-Capacity Failures
------------------------------------

**Insufficient resources**:

.. code-block:: console

   $ canary run my_test.pyt
   Error: insufficient slots on node hostname of cpus (requested 16, available 8)

Solutions:

- Reduce resource requirements in test parameters
- Increase resource pool capacity
- Run fewer concurrent tests

Check resource pool:

.. code-block:: console

   $ canary config show resource_pool

Debugging Timeouts
------------------

**Timeout errors**:

.. code-block:: console

   $ canary status -rt
   ID      Name          Session      Exit Code  Duration  Status    Details
   a1b2c3  slow_test.pyt session1     124         600.50    TIMEOUT   Exceeded 600s limit

Solutions:

- Increase timeout in configuration:

  .. code-block:: yaml

     canary:
       run:
         timeout:
           long: 1800.0

- Use ``-t`` flag for specific timeout:

  .. code-block:: console

     $ canary run -t 1800 slow_test.pyt

Debugging Worker Issues
-----------------------

**Worker death**:

.. code-block:: console

   $ canary run my_test.pyt
   Error: Worker process died unexpectedly

Solutions:

- Reduce ``--workers`` count
- Check system resources (memory, CPU)
- Enable debug logging:

  .. code-block:: console

     $ canary -d run my_test.pyt

Debugging Interrupted/Cancelled Sessions
-----------------------------------------

**Session interruption**:

.. code-block:: console

   $ canary status
   ID      Name          Session      Exit Code  Duration  Status      Details
   a1b2c3  test.pyt      session1     130         42.50     CANCELLED  User interrupt

Solutions:

- Rerun with ``--only=notrun``:

  .. code-block:: console

     $ canary run --only=notrun .

- Resume session:

  .. code-block:: console

     $ canary run --session=session1 .

Debugging Stale Views
---------------------

**Stale view symptoms**:

- Results not appearing in TestResults directory
- Inconsistent status between view and database

Solutions:

- Rebuild view:

  .. code-block:: console

     $ canary view --rebuild

- Check view configuration:

  .. code-block:: console

     $ canary config show workspace.view

Debugging Corrupt or Missing Lock Files
----------------------------------------

**Missing lock file**:

.. code-block:: console

   $ canary log JOB_ID
   Error: testcase.lock not found

Solutions:

- Rerun the job:

  .. code-block:: console

     $ canary run JOB_ID

- Check workspace integrity:

  .. code-block:: console

     $ canary workspace verify

Using Debug Flags
-----------------

**Enable debug mode**:

.. code-block:: console

   $ canary -d run my_test.pyt
   $ canary --debug run my_test.pyt

**Verbose logging**:

.. code-block:: console

   $ canary -v run my_test.pyt
   $ canary --verbose run my_test.pyt

**Debug configuration**:

.. code-block:: yaml

   canary:
     debug: true
     log_level: DEBUG

When to Rerun with Specific Strategies
---------------------------------------

**Rerun only failed tests**:

.. code-block:: console

   $ canary run --only=failed .

**Rerun only not-run tests**:

.. code-block:: console

   $ canary run --only=notrun .

**Rerun with resource constraints**:

.. code-block:: console

   $ canary run --workers=4 -r cpus=8 .

**Rerun with timeout override**:

.. code-block:: console

   $ canary run -t 1800 slow_test.pyt

Advanced Debugging Techniques
-----------------------------

**Query measurements**:

.. code-block:: console

   $ canary query -j JOB_ID .measurements
   {"duration": 42.5, "memory_usage": 1024, "custom_metric": 0.95}

**Inspect dependency graph**:

.. code-block:: console

   $ canary describe JOB_ID
   composite_test.pyt
   ├── child1.pyt (PASSED)
   ├── child2.pyt (PASSED)
   └── child3.pyt (FAILED)

**Check resource allocation**:

.. code-block:: console

   $ canary query -j JOB_ID .resources
   {
     "cpus": [{"node": "host1", "id": "0", "slots": 4}],
     "gpus": [{"node": "host1", "id": "0", "slots": 2}]
   }

Debugging Best Practices
------------------------

**Reproducible Debugging**:

- Document exact commands used
- Capture full output and logs
- Note environment and configuration

**Isolation**:

- Test with minimal job sets
- Use ``--workers=1`` to eliminate concurrency issues
- Disable plugins when debugging core issues

**Progressive Complexity**:

- Start with simple tests
- Gradually increase complexity
- Identify exact failure point

**Log Preservation**:

- Archive logs before rerunning
- Use unique session names for debugging runs
- Capture both stdout and stderr

Debugging Checklist
-------------------

1. ✅ Check overall status with ``canary status``
2. ✅ Inspect specific job logs with ``canary log``
3. ✅ Examine lock files with ``canary query``
4. ✅ Locate execution directories with ``canary location``
5. ✅ Verify resource availability with ``canary config show resource_pool``
6. ✅ Check dependency relationships with ``canary describe``
7. ✅ Review configuration with ``canary config show``
8. ✅ Enable debug logging if needed
9. ✅ Rerun with appropriate ``--only`` strategy
10. ✅ Document findings and solutions

See Also
--------

- :doc:`concepts`: Core architectural concepts
- :doc:`running`: Execution configuration and strategies
- :doc:`results`: Result inspection and analysis
- :doc:`query`: Advanced querying capabilities
- :doc:`/reference/commands.status`: Status command reference
- :doc:`/reference/commands.log`: Log command reference
- :doc:`/reference/commands.location`: Location command reference
- :doc:`/reference/commands.query`: Query command reference