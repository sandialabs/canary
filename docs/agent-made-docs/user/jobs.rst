.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Jobs
====

This document explains the core job-related objects in Canary: ``JobSpecIR``, ``JobSpec``, and ``Job``. It describes their lifecycle, relationships, and key attributes.

JobSpecIR
---------

**JobSpecIR** (Job Specification Intermediate Representation) is the generator-specific output produced during the discovery phase. It represents a job before dependency resolution and contains:

- **Job identity and metadata**: Name, family, parameters
- **Resource requirements**: CPU, GPU, memory, timeout constraints
- **Dependencies**: Dependency selectors with patterns and conditions
- **Execution directives**: Commands, environment variables, working directories
- **Generator-specific attributes**: Format-specific metadata and directives

JobSpecIR objects are lightweight and may contain template variables that need expansion. They are emitted by job generators (such as ``canary_pyt``, ``canary_cmake``, or ``canary_vvtest``) during the collection phase.

When JobSpecIR Exists
~~~~~~~~~~~~~~~~~~~~~

JobSpecIR objects exist temporarily during:

1. **Discovery phase**: When generators scan source files and create initial job definitions
2. **Collection phase**: When Canary collects JobSpecIR objects from all generators
3. **Resolution phase**: When Canary converts JobSpecIR to JobSpec through dependency resolution

JobSpecIR objects do not persist beyond the resolution phase; they are converted to JobSpec objects for execution planning.

JobSpec
-------

**JobSpec** is the canonical, resolved job specification used by Canary core. It represents a complete, executable job definition with all dependencies resolved and contains:

- **Unique job identifier**: SHA256-based ID derived from job attributes
- **Execution command and arguments**: What to run and with what parameters
- **Resource requirements**: CPU cores, GPU devices, memory, nodes, timeout
- **Dependency specifications**: Resolved SpecDependency objects with conditions
- **Environment requirements**: Environment variables and module loading
- **Expected outcomes**: Validation rules and baseline comparisons
- **Execution paths**: Working directories and output locations

JobSpec objects are serializable and stored in the workspace database. They form the basis for dependency graph construction and execution planning.

JobSpec Creation Process
~~~~~~~~~~~~~~~~~~~~~~~~

The conversion from JobSpecIR to JobSpec involves:

1. **Dependency resolution**: Matching dependency selectors against available JobSpecs
2. **Parameter expansion**: Resolving template variables in dependency patterns
3. **Resource calculation**: Computing derived resource parameters (e.g., nodes from CPU/GPU requirements)
4. **ID generation**: Creating unique, deterministic job identifiers
5. **Validation**: Ensuring all required fields are present and valid

This process is handled by the ``JobSpecIR.finalize()`` method, which takes a lookup dictionary of resolved JobSpecs and produces a complete JobSpec.

When JobSpec Exists
~~~~~~~~~~~~~~~~~~~

JobSpec objects exist in multiple contexts:

1. **Workspace database**: Persistent storage of all discovered job specifications
2. **Selection tags**: Groupings of JobSpecs for targeted execution
3. **Session planning**: Input to session construction and job instantiation
4. **Dependency graph**: Nodes in the execution dependency graph

JobSpec objects are immutable once created and can be reused across multiple sessions.

Job
---

A **Job** is the executable runtime instance created from a JobSpec. It represents the active, running state of a job within a session and includes:

- **JobSpec reference**: The specification this job executes
- **Workspace context**: Execution environment and file system locations
- **Runtime state**: Current phase (PENDING, STAGING, RUNNING, FINISHING, DONE)
- **Status tracking**: Execution outcome and completion status
- **Resource allocation**: Assigned CPU/GPU resources and environment
- **Timekeeping**: Timing measurements for all execution phases
- **Dependencies**: Runtime references to dependent Job objects

Jobs are created by the session during execution planning and are responsible for actual command execution.

Job Lifecycle Phases
~~~~~~~~~~~~~~~~~~~~

Jobs progress through several phases during execution:

.. list-table:: Job Phases
   :widths: 25 75
   :header-rows: 1

   * - Phase
     - Description
   * - **PENDING**
     - Initial state; job is waiting for dependencies or resources
   * - **STAGING**
     - Workspace preparation; file copying/linking and environment setup
   * - **RUNNING**
     - Active execution; command is running in the execution environment
   * - **FINISHING**
     - Post-execution processing; result collection and cleanup
   * - **DONE**
     - Terminal state; execution complete with final status

Job Identity
------------

Each job has multiple identifiers that serve different purposes:

- **ID**: Unique SHA256-based identifier (e.g., ``"a1b2c3..."``)
  - Used for database storage and result tracking
  - Deterministic based on job attributes
  - Format: ``[A-Za-z0-9_.:=+\/\-]+``

- **Name**: Parameterized job name (e.g., ``"test_case[a=1,b=2]"``)
  - Human-readable identifier with parameters
  - Format: ``family.parameter=value.parameter=value``

- **Fullname**: Resolved path-based name (e.g., ``"path/to/test_case[a=1,b=2]"``)
  - Includes relative path from workspace root
  - Used for display and reporting

- **Family**: Base job name without parameters (e.g., ``"test_case"``)
  - Shared by all parameterized variants of the same job

Job Statuses
------------

Jobs report their execution status through the ``Status`` object, which combines:

- **Category**: High-level outcome (PASS, FAIL, CANCEL, SKIP, NONE)
- **Outcome**: Specific result (SUCCESS, XFAIL, DIFFED, FAILED, TIMEOUT, etc.)
- **Reason**: Human-readable explanation (if applicable)
- **Code**: Exit code or error number

Common status combinations:

.. list-table:: Common Job Statuses
   :widths: 25 25 50
   :header-rows: 1

   * - Category
     - Outcome
     - Meaning
   * - PASS
     - SUCCESS
     - Job completed successfully with exit code 0
   * - PASS
     - XFAIL
     - Job failed as expected (expected failure)
   * - PASS
     - XDIFF
     - Job diffed as expected (expected difference)
   * - FAIL
     - FAILED
     - Job completed with non-zero exit code
   * - FAIL
     - DIFFED
     - Job completed with diff exit code (64)
   * - FAIL
     - TIMEOUT
     - Job exceeded its timeout
   * - SKIP
     - SKIPPED
     - Job was skipped due to conditions or dependencies
   * - CANCEL
     - CANCELLED
     - Job was cancelled by user or system

Job Measurements
----------------

Jobs collect timing and resource measurements through the ``Timekeeper`` and ``Measurements`` objects:

- **Timekeeper**: Tracks execution timing for all phases
  - Submission time (when job was queued)
  - Stage time (workspace preparation duration)
  - Start time (when execution began)
  - Stop time (when execution ended)
  - Total runtime

- **Measurements**: Custom metrics and execution data
  - Resource utilization (CPU, memory, I/O)
  - Custom metrics reported by the job
  - Performance counters and statistics

Execution Directories
---------------------

Each job executes in a dedicated workspace with specific directory structure:

- **Session directory**: ``.canary/sessions/{session_name}/``
  - Contains all jobs for a specific execution session

- **Job workspace**: ``.canary/sessions/{session_name}/{exec_path}/``
  - Dedicated directory for this job instance
  - Contains ``testcase.lock`` with job state
  - Contains stdout/stderr logs
  - Contains execution artifacts

- **View path**: ``TestResults/{view_path}/``
  - Symlink/hardlink location in the results view
  - Mirrors source tree structure for easy navigation

Assets and Artifacts
--------------------

Jobs manage file resources through assets and artifacts:

- **Assets**: Input files required for execution
  - Copied or linked from source locations
  - Specified with action (copy, link, none)
  - Required before execution begins

- **Artifacts**: Output files produced by execution
  - Collected based on glob patterns
  - Conditional collection (always, never, on_failure, on_success)
  - Preserved for result analysis and reporting

Relationship to Generator-Specific Documentation
-------------------------------------------------

This document describes the core job objects at the framework level. For generator-specific details, see the extension documentation:

- **canary_pyt**: Python-based job definitions (extension)
- **canary_cmake**: CMake/CTest integration (extension)
- **canary_vvtest**: VVTest compatibility (extension)

Each generator produces JobSpecIR objects that conform to the core framework requirements while supporting format-specific features and directives.

Job Object Summary
------------------

.. list-table:: Job Object Comparison
   :widths: 25 25 25 25
   :header-rows: 1

   * - Object
     - Phase
     - Mutability
     - Persistence
   * - JobSpecIR
     - Discovery/Collection
     - Mutable
     - Temporary
   * - JobSpec
     - Resolution/Planning
     - Immutable
     - Database
   * - Job
     - Execution
     - Mutable
     - Session-only
