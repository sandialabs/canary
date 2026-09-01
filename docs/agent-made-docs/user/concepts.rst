.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Core Concepts
=============

Canary's Architecture
---------------------

Canary follows a plugin-based architecture with a clear pipeline for job execution:

.. code-block:: text

   User job definition
     -> Job Generator
       -> JobSpecIR / JobSpec
         -> Dependency Resolution
           -> Resolved JobSpec Graph
             -> Session constructs Job objects
               -> Resource-aware Execution
                 -> Persistence, Query, and Reporting

This pipeline ensures a consistent processing model while allowing flexibility at each stage through plugins.

Job Generator
-------------

A **job generator** is a plugin that interprets user-facing job definitions and emits standardized job specifications. Generators are responsible for:

- Discovering job definitions in source files
- Parsing job specifications and directives
- Emitting ``JobSpecIR`` or ``JobSpec`` objects
- Providing metadata about the jobs

Canary core does not define a universal job-definition file format. Instead, it relies on generators to handle different input formats and convert them to a common intermediate representation.

JobSpecIR
---------

**JobSpecIR** (Job Specification Intermediate Representation) is a lightweight, generator-specific representation of a job. It contains:

- Job identity and metadata
- Resource requirements
- Dependencies
- Execution directives
- Generator-specific attributes

Generators emit ``JobSpecIR`` objects, which are then converted to ``JobSpec`` objects by Canary core.

JobSpec
-------

**JobSpec** is the canonical job specification format used by Canary core. It represents a fully-resolved job definition with:

- Unique job identifier
- Execution command and arguments
- Resource requirements (CPU, GPU, memory, etc.)
- Dependency specifications
- Timeout and scheduling constraints
- Environment requirements
- Expected outcomes and validation rules

JobSpec objects form the basis for dependency resolution and execution planning.

Job
---

A **Job** is the executable instance created from a ``JobSpec``. The Canary session constructs Job objects from resolved JobSpecs and manages their execution. Jobs are responsible for:

- Executing the specified command
- Managing resources during execution
- Capturing output and results
- Handling timeouts and failures
- Reporting status back to the session

Workspace
---------

A **workspace** is the execution environment for a job. It includes:

- Working directory
- Input files and dependencies
- Output directories
- Temporary storage
- Environment variables
- Resource allocations

Canary manages workspaces to ensure isolation and reproducibility across job executions.

Session
-------

The **session** is the central coordinator that manages the entire job lifecycle:

- Discovers and collects job definitions
- Resolves dependencies between jobs
- Constructs the execution graph
- Schedules jobs based on resources and dependencies
- Manages job execution and monitoring
- Handles failures and retries
- Persists results and status
- Provides query and reporting interfaces

Resource Pool
-------------

A **resource pool** represents the available computational resources for job execution. It includes:

- CPU cores
- GPU devices
- Memory capacity
- Storage resources
- Network resources
- Specialized hardware

Canary performs resource-aware scheduling to efficiently utilize available resources while respecting job requirements and constraints.

Dependency Graph
----------------

The **dependency graph** represents relationships between jobs. It enables:

- Execution ordering based on dependencies
- Failure propagation and handling
- Resource-aware scheduling
- Parallel execution where possible
- Deadlock detection and resolution

Dependencies can be explicit (specified by the user) or implicit (inferred by Canary based on resource usage or execution patterns).

Status and Result
-----------------

Each job has a **status** that tracks its execution state:

- **pending**: Job is waiting for dependencies or resources
- **running**: Job is currently executing
- **success**: Job completed successfully
- **failure**: Job completed with errors
- **skipped**: Job was not executed due to conditions
- **timeout**: Job exceeded its time limit

Results include execution metrics, output artifacts, and validation outcomes.

Persistence
-----------

Canary persists job specifications, execution results, and status information to enable:

- Resuming interrupted sessions
- Querying historical results
- Generating reports and summaries
- Auditing and debugging
- Long-term result tracking

Reporting
---------

Canary provides reporting capabilities through plugins that can:

- Generate execution summaries
- Create detailed result reports
- Export data in various formats
- Integrate with external systems (CDash, etc.)
- Provide visualization and analysis tools

Plugin Architecture
-------------------

Canary's plugin architecture enables extensibility at multiple levels:

- **Job Generators**: Add support for new input formats
- **Reporters**: Add new output and reporting formats
- **Scheduler Backends**: Add new execution backends
- **Resource Backends**: Add specialized resource management
- **External Integrations**: Connect with other tools and systems

Plugins register themselves with Canary core and participate in the job lifecycle through well-defined interfaces.
