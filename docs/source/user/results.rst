.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Inspecting Results
==================

This document explains how to inspect and analyze Canary execution results, covering status information, output files, and result navigation.

Status Categories and Outcomes
------------------------------

Canary reports job status using a two-level system:

**Categories** (high-level):

- **PASS**: Job completed successfully
- **FAIL**: Job completed with errors
- **CANCEL**: Job was cancelled
- **SKIP**: Job was skipped
- **NONE**: Status not set

**Outcomes** (specific):

.. list-table:: Status Outcomes
   :widths: 25 75
   :header-rows: 1

   * - Outcome
     - Meaning
   * - SUCCESS
     - Job completed with exit code 0
   * - XFAIL
     - Job failed as expected (expected failure)
   * - XDIFF
     - Job diffed as expected (expected difference)
   * - DIFFED
     - Job completed with diff exit code (64)
   * - FAILED
     - Job completed with non-zero exit code
   * - ERROR
     - Job encountered execution error
   * - BROKEN
     - Job is broken or misconfigured
   * - TIMEOUT
     - Job exceeded its timeout
   * - INVALID
     - Job has invalid configuration
   * - CANCELLED
     - Job was cancelled by user/system
   * - INTERRUPTED
     - Job was interrupted (e.g., Ctrl+C)
   * - SKIPPED
     - Job was skipped due to conditions
   * - BLOCKED
     - Job blocked by failed dependencies

Phases versus Statuses
----------------------

**Phases** represent execution lifecycle:

- PENDING: Waiting for dependencies/resources
- STAGING: Workspace preparation
- RUNNING: Active execution
- FINISHING: Post-execution processing
- DONE: Terminal state

**Statuses** represent completion outcomes:

- Categories and outcomes (as above)
- Set when job reaches DONE phase
- Persisted in database and results

Return Codes
------------

Canary uses return codes for process communication:

.. list-table:: Return Codes
   :widths: 25 75
   :header-rows: 1

   * - Code
     - Meaning
   * - 0
     - All jobs completed successfully
   * - 1
     - General execution failure
   * - 2
     - Configuration or setup error
   * - 3
     - Resource allocation failure
   * - 4
     - Dependency resolution failure
   * - 7
     - Empty test set (no jobs to run)
   * - Other
     - Specific error codes from plugins

canary status
-------------

Inspect execution status with the ``status`` command:

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary run ./basic, python3 -m canary status -rA]
   :cwd: /examples

Status output includes:

- Job ID and name
- Session information
- Exit code
- Duration
- Status category and outcome

Durations
---------

Analyze execution timing:

.. code-block:: console

   # Show durations for all jobs
   canary status --durations

   # Show top N slowest jobs
   canary status --durations 10

   # Show durations for specific status
   canary status --durations -rf

Duration information helps identify:

- Performance bottlenecks
- Slow tests needing optimization
- Resource contention issues
- Execution patterns

canary log
----------

View job output with the ``log`` command:

.. code-block:: console

   # View log for specific job
   canary log JOB_ID

   # View log with context
   canary log -v JOB_ID

   # View compressed log (large outputs)
   canary log -c JOB_ID

Log files contain:

- Standard output (stdout)
- Standard error (stderr) if separate
- Execution timestamps
- Environment information
- Command line used

canary location
---------------

Find job execution directories:

.. code-block:: console

   # Get execution directory path
   canary location JOB_ID

   # Navigate to execution directory
   cd $(canary location JOB_ID)

Location command returns:

- Path to job's execution directory
- Contains ``testcase.lock`` and output files
- Useful for manual inspection and debugging

Output Files
------------

Each job produces standard output files:

**canary-out.txt**:

- Primary output file
- Contains stdout from job execution
- Includes timestamps and execution context
- Format: ``[YYYY-MM-DD-HH:MM:SS.ffffff] message``

**Additional files**:

- ``JOB.stderr``: Separate stderr if configured
- ``testcase.lock``: Job state and results
- Artifacts: Output files matching artifact patterns

testcase.lock
-------------

The job state file contains:

.. code-block:: json

   {
     "spec": "...",
     "workspace": "...",
     "dependencies": "...",
     "variables": "...",
     "allocation": "...",
     "rparameters": "...",
     "mask": "...",
     "status": "...",
     "state": "...",
     "timekeeper": "...",
     "measurements": "...",
   }

This file should not be edited manually.

session.lock
------------

The session manifest contains:

.. code-block:: json

   {
     "name": "session_name",
     "prefix": "session_path",
     "job_ids": ["job1", "job2", "..."],
     "returncode": 0,
     "started_on": "ISO_timestamp",
     "finished_on": "ISO_timestamp",
     "argv": ["canary", "run", "..."],
     "config": { "..." },
     "measurements": { "..." }
   }

Session manifest provides:

- Session metadata and timing
- Job list and execution order
- Configuration snapshot
- Performance measurements

Results Views
-------------

**TestResults/**: Symlink/hardlink tree for easy navigation:

.. code-block:: text

   TestResults/
   ├── path/
   │   └── to/
   │       └── job_name/          # Symlink to session job directory
   │           ├── canary-out.txt  # stdout
   │           ├── testcase.lock   # Job state
   │           └── artifacts/      # Output files
   └── another/
       └── test.pyt/              # Another job
           └── ...

Views enable:

- Intuitive result navigation
- Source-tree organization
- Quick access to latest results
- Manual inspection workflow

Artifacts
---------

Jobs produce artifacts based on configuration:

.. code-block:: console

   # List artifacts for a job
   ls $(canary location JOB_ID)/artifacts/

Artifact collection:

- **Always**: Collected regardless of status
- **Never**: Never collected
- **On failure**: Collected only if job fails
- **On success**: Collected only if job succeeds

Artifacts are preserved in:

- Job execution directory
- TestResults view (if applicable)
- Database records

Reports
-------

Canary generates various report formats:

.. code-block:: console

   # Generate HTML report
   canary report html

   # Generate JSON report
   canary report json

   # Generate CDash report
   canary report cdash

Reports provide:

- Execution summaries
- Statistical analysis
- Trend visualization
- Integration with external systems

Relationship to Query and Persistence
-------------------------------------

Results are stored in multiple locations:

.. list-table:: Result Storage
   :widths: 25 75
   :header-rows: 1

   * - Location
     - Purpose
   * - workspace.sqlite3
     - Permanent result storage
   * - session.lock
     - Session metadata
   * - testcase.lock
     - Individual job results
   * - TestResults/
     - Navigation view
   * - .canary/cache/
     - Performance history

Query mechanisms:

- ``canary status``: Query current results
- ``canary log``: View job output
- ``canary location``: Find execution directories
- Database queries: Advanced result analysis

Result Inspection Workflow
--------------------------

1. **Check overall status**: ``canary status``
2. **Identify failures**: ``canary status -rf``
3. **View failure details**: ``canary log FAILED_JOB_ID``
4. **Locate execution**: ``canary location FAILED_JOB_ID``
5. **Inspect artifacts**: ``ls $(canary location JOB_ID)/artifacts/``
6. **Analyze durations**: ``canary status --durations``
7. **Generate reports**: ``canary report``

Result Analysis Tips
--------------------

1. **Start with summary**: ``canary status`` for overview
2. **Focus on failures**: Use ``-rf`` to filter failed jobs
3. **Check slow jobs**: ``--durations`` identifies bottlenecks
4. **Review logs**: ``canary log`` for detailed output
5. **Inspect state**: ``testcase.lock`` for job metadata
6. **Navigate views**: TestResults for intuitive browsing
7. **Generate reports**: For comprehensive analysis

Result Status Lifecycle
-----------------------

1. **Initial**: Status unset (NONE)
2. **Execution**: Status updates during execution
3. **Completion**: Final status set (SUCCESS, FAILED, etc.)
4. **Persistence**: Status stored in database
5. **Query**: Status available via commands
6. **Reporting**: Status included in reports

Common Result Patterns
----------------------

.. list-table:: Result Patterns
   :widths: 25 75
   :header-rows: 1

   * - Pattern
     - Likely Cause
   * - All SUCCESS
     - Healthy test suite
   * - Some XFAIL
     - Expected failures documented
   * - Random FAILED
     - Flaky tests or resource issues
   * - All TIMEOUT
     - Timeout configuration too tight
   * - Many BLOCKED
     - Dependency chain issues
   * - All SKIPPED
     - Filter criteria too restrictive

Result Troubleshooting
----------------------

.. list-table:: Result Issues
   :widths: 25 75
   :header-rows: 1

   * - Issue
     - Solution
   * - Missing results
     - Check session completion
   * - Inconsistent status
     - Verify database integrity
   * - Empty TestResults
     - Check view generation
   * - Slow queries
     - Optimize database or filters
   * - Corrupted logs
     - Check filesystem permissions

Result Best Practices
---------------------

1. **Regular review**: Check results after each execution
2. **Failure analysis**: Investigate failures promptly
3. **Performance monitoring**: Track durations over time
4. **Result preservation**: Backup important session data
5. **View maintenance**: Ensure TestResults is updated
6. **Report generation**: Create reports for record-keeping
7. **Database backup**: Protect historical results

Result Examples
---------------

**Basic status check**:

.. code-block:: console

   # Quick overview
   canary status

   # Detailed view
   canary status -v

**Failure investigation**:

.. code-block:: console

   # Find failed jobs
   canary status -rf

   # View specific failure
   canary log failed_job_id

   # Locate failure directory
   cd $(canary location failed_job_id)

**Performance analysis**:

.. code-block:: console

   # Identify slow jobs
   canary status --durations 5

   # Analyze specific job
   canary log slow_job_id

**Result navigation**:

.. code-block:: console

   # Browse TestResults
   ls -R TestResults/

   # Find specific result
   find TestResults -name "pattern" -type d

For complete command reference, see:

- :doc:`/reference/commands.status`
- :doc:`/reference/commands.log`
- :doc:`/reference/commands.location`
