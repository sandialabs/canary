.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Sessions
========

A **session** represents a specific execution run of Canary jobs. It coordinates job execution, manages runtime state, and tracks results within a workspace.

What a Session Is
-----------------

A Canary session is:

- A coordinated execution of one or more jobs
- A runtime context with shared configuration and resources
- A container for job results and measurements
- A unit of work with lifecycle management
- An atomic execution unit for reporting and analysis

Sessions are created within workspaces and manage the complete execution lifecycle from job dispatch to result persistence.

Session Structure
-----------------

Sessions are stored in the workspace's ``sessions/`` directory:

.. code-block:: text

   .canary/
   └── sessions/
       └── {session_name}/
           ├── session.lock        # Session manifest
           ├── job1_dir/          # Job execution directories
           │   ├── testcase.lock   # Job state
           │   ├── canary-out.txt  # stdout
           │   └── artifacts/      # Output files
           ├── job2_dir/
           │   ├── testcase.lock
           │   ├── canary-out.txt
           │   └── artifacts/
           └── ...

Session Name
------------

Session names identify individual execution runs:

- **Default format**: ISO timestamp with microseconds (e.g., ``2024-01-15T12-34-56.789012``)
- **Custom names**: Can be specified for special purposes
- **Unique requirement**: Must be unique within a workspace
- **Filesystem-safe**: Used as directory names

Session names appear in:

- Directory paths (``.canary/sessions/{name}/``)
- Session manifest (``session.lock``)
- Database records
- Reports and output

Session Directory
-----------------

Each session has a dedicated directory under ``.canary/sessions/``:

- Contains all jobs executed in that session
- Organized by job execution paths
- Isolated from other sessions
- Preserved for historical analysis

Session directories are created automatically when sessions start.

session.lock
------------

The ``session.lock`` file is the session manifest:

.. code-block:: json

   {
     "name": "2024-01-15T12-34-56.789012",
     "prefix": ".canary/sessions/2024-01-15T12-34-56.789012",
     "job_ids": ["job_id_1", "job_id_2", "job_id_3"],
     "returncode": 0,
     "started_on": "2024-01-15T12:34:56.789012",
     "finished_on": "2024-01-15T12:35:12.345678",
     "argv": ["canary", "run", "tag_name"],
     "config": {
       "canary": { "..." }
     },
     "measurements": {
       "total_jobs": 42,
       "successful": 40,
       "failed": 2,
       "runtime": 345.678
     }
   }

This file should not be edited manually.

Latest Session Reference
------------------------

The latest session is referenced in ``.canary/refs/latest``:

.. code-block:: text

   ../sessions/2024-01-15T12-34-56.789012

This relative path reference:

- Points to the most recently completed session
- Enables quick access to latest results
- Updated automatically after each session
- Used by default when no specific session is requested

Session Lifecycle
-----------------

Sessions progress through a well-defined lifecycle:

1. **Creation**: Session object instantiated with job list
2. **Initialization**: Workspace preparation and validation
3. **Execution**: Job dispatch, monitoring, and management
4. **Completion**: Result collection and finalization
5. **Persistence**: Database updates and session manifest
6. **Reporting**: Result analysis and output generation

Session Hooks
-------------

Canary provides lifecycle hooks for session management:

- **canary_sessionstart**: Called when session execution begins
- **canary_sessionfinish**: Called when session execution completes

These hooks enable plugins to:

- Initialize session-specific resources
- Monitor session progress
- Collect session-level measurements
- Generate custom reports and analysis
- Clean up session resources

Session Return Code
-------------------

Sessions report their overall status through return codes:

- **0**: All jobs completed successfully
- **1**: General execution failure
- **2**: Configuration or setup error
- **3**: Resource allocation failure
- **4**: Dependency resolution failure
- **Other**: Specific error codes from plugins or extensions

The return code is stored in ``session.lock`` and available for automation.

Session Measurements
--------------------

Sessions collect measurements throughout execution:

- **Total jobs**: Number of jobs in the session
- **Successful jobs**: Jobs with PASS category status
- **Failed jobs**: Jobs with FAIL category status
- **Skipped jobs**: Jobs with SKIP category status
- **Runtime**: Total session execution time
- **Resource utilization**: Aggregate CPU, GPU, memory usage
- **Custom metrics**: Plugin-specific measurements

Measurements are stored in ``session.lock`` and the workspace database.

Relationship Between Sessions, Jobs, and Database
-------------------------------------------------

Sessions coordinate the interaction between jobs and the workspace database:

1. **Job Selection**: Session receives JobSpecs from workspace
2. **Job Instantiation**: Session creates Job objects from JobSpecs
3. **Execution**: Session manages Job execution and monitoring
4. **Result Collection**: Session gathers Job results and status
5. **Database Update**: Session persists results to workspace database
6. **View Update**: Session updates the TestResults view

This relationship ensures consistent state across all components.

Session and Job Relationship
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: Session-Job Relationship
   :widths: 30 70
   :header-rows: 1

   * - Aspect
     - Relationship
   * - **JobSpecs**
     - Session receives JobSpecs from workspace selection
   * - **Jobs**
     - Session creates executable Job instances from JobSpecs
   * - **Execution**
     - Session manages job dispatch and resource allocation
   * - **Dependencies**
     - Session ensures dependency order is respected
   * - **Results**
     - Session collects and aggregates job results
   * - **Persistence**
     - Session writes final results to database

Session and Database Relationship
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: Session-Database Relationship
   :widths: 30 70
   :header-rows: 1

   * - Operation
     - Interaction
   * - **JobSpec loading**
     - Session queries database for selected JobSpecs
   * - **Result storage**
     - Session writes Job results to database after execution
   * - **Historical data**
     - Session can query previous results for comparison
   * - **Cache updates**
     - Session updates job timing cache after successful runs
   * - **View management**
     - Session updates latest view reference after completion

Reusing and Rerunning Sessions
------------------------------

Canary supports session reuse for incremental execution:

**Rerun Strategies:**

- **not_pass**: Run jobs that did not pass in previous execution (default)
- **all**: Run all jobs regardless of previous status
- **failed**: Run only jobs that failed previously
- **none**: Run no jobs (useful for testing session setup)

**Session Reuse:**

.. code-block:: python

   from _canary.workspace import Workspace

   ws = Workspace.load()

   # Rerun a specific session with new strategy
   session = ws.run(specs, session="previous_session_name", only="failed")

**In-Place Execution:**

.. code-block:: python

   # Reuse existing job directories (careful: can cause conflicts)
   session = ws.run(specs, session="existing_session", inplace=True)

Session Management Commands
---------------------------

Common session management operations:

.. list-table:: Session Commands
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
     - Clean up old session directories
   * - ``canary report``
     - Generate reports from session results

Session Best Practices
----------------------

1. **Meaningful session names**: Use descriptive names for important sessions
2. **Regular cleanup**: Remove old sessions to save disk space
3. **Incremental execution**: Use rerun strategies for efficient development
4. **Result analysis**: Review session measurements and failures
5. **Configuration consistency**: Ensure consistent configuration across sessions
6. **Resource management**: Monitor resource utilization per session
7. **Historical tracking**: Preserve important sessions for analysis

Session Execution Flow
----------------------

1. **Session creation**: Instantiate Session object with job list
2. **Workspace preparation**: Create session directory and validate jobs
3. **Hook invocation**: Call ``canary_sessionstart`` hooks
4. **Job dispatch**: Submit jobs to execution queue
5. **Monitoring**: Track job progress and resource usage
6. **Result collection**: Gather job status and measurements
7. **Database update**: Persist results to workspace database
8. **View update**: Refresh TestResults view
9. **Hook invocation**: Call ``canary_sessionfinish`` hooks
10. **Completion**: Write final session manifest

Session Troubleshooting
-----------------------

Common session issues and resolutions:

.. list-table:: Session Troubleshooting
   :widths: 25 75
   :header-rows: 1

   * - Issue
     - Resolution
   * - Session fails to start
     - Check workspace configuration and job validity
   * - Jobs stuck in PENDING
     - Verify resource availability and dependencies
   * - Database locked errors
     - Ensure no other Canary process is running
   * - View not updated
     - Check session completion and permissions
   * - High return code
     - Review session.log and job outputs
   * - Missing results
     - Verify session completed successfully

Session Configuration
---------------------

Sessions inherit configuration from multiple sources (in priority order):

1. **Command-line arguments**: Highest priority
2. **Session-specific configuration**: In ``session.lock``
3. **Workspace configuration**: From ``config.yaml``
4. **User configuration**: From ``~/.canary/config.yaml``
5. **Default configuration**: Built-in Canary defaults

This hierarchy allows flexible customization while maintaining consistency.

Session Isolation
-----------------

Canary ensures session isolation through:

- **Directory separation**: Each session has dedicated directories
- **Resource management**: Resource pool prevents conflicts
- **Database transactions**: Atomic operations maintain consistency
- **Process isolation**: Jobs execute in separate processes
- **Environment isolation**: Each job gets dedicated environment

This isolation prevents interference between concurrent or sequential sessions.

Session Performance
-------------------

Session performance depends on:

- **Job count**: Number of jobs in the session
- **Dependency complexity**: Depth and breadth of dependency graph
- **Resource availability**: CPU, GPU, memory constraints
- **I/O performance**: Disk speed for workspace operations
- **Job characteristics**: Runtime and resource requirements

Optimization strategies:

- Use rerun strategies to minimize redundant execution
- Balance job granularity (not too fine, not too coarse)
- Optimize dependency graphs for parallelism
- Monitor and tune resource allocation
- Use caching for repeated operations

Session Reporting
-----------------

Sessions provide data for comprehensive reporting:

- **Execution summaries**: Overall success/failure statistics
- **Timing analysis**: Job runtime distribution and trends
- **Resource utilization**: CPU, GPU, memory usage patterns
- **Failure analysis**: Detailed breakdown of failed jobs
- **Historical comparison**: Performance across multiple sessions
- **Custom reports**: Plugin-specific analysis and visualization

Reports can be generated during or after session execution.
