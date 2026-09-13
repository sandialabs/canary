.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-concepts:

Core concepts
=============

``canary`` follows a plugin-based architecture with a clear pipeline for job execution:

.. code-block:: text

   User job definition
     -> Job Generator
       -> JobSpecIR / JobSpec
         -> Dependency Resolution
           -> Resolved JobSpec Graph
             -> Session constructs Job objects
               -> Resource-aware Execution
                 -> Persistence, Query, and Reporting

This pipeline ensures a consistent processing model while allowing flexibility at each
stage through plugins.

Job Generator
-------------

A **job generator** is a plugin that interprets user-facing job definitions and emits
standardized job specifications.  Generators are responsible for:

- Discovering job definitions in source files
- Parsing job specifications and directives
- Emitting :ref:`JobSpecIR <basics-jobspecir>` or :ref:`JobSpec <basics-jobspec>` objects
- Providing metadata about the jobs

``canary`` core does not define a universal job-definition file format.  Instead, it
relies on generators to handle different input formats and convert them to a common
intermediate representation.  See :ref:`extending-generator` for how to write one,
and :ref:`basics-concepts-generators` below for the bundled generators.

.. _basics-jobspecir:

JobSpecIR
---------

**JobSpecIR** (Job Specification Intermediate Representation) is a lightweight,
generator-specific representation of a job.  It contains:

- Job identity and metadata
- Resource requirements
- Dependencies
- Execution directives
- Generator-specific attributes

Generators emit ``JobSpecIR`` objects, which are then converted to ``JobSpec`` objects
by ``canary`` core during the resolution phase.  JobSpecIR objects are temporary and do
not persist beyond dependency resolution.

.. _basics-jobspec:

JobSpec
-------

**JobSpec** is the canonical job specification used by ``canary`` core.  It represents
a fully-resolved job definition with:

- Unique, deterministic job identifier (SHA256-based)
- Execution command and arguments
- Resource requirements (CPU, GPU, etc.)
- Resolved dependency specifications
- Timeout and scheduling constraints
- Environment requirements
- Expected outcomes and validation rules

JobSpec objects are serializable and stored in the workspace database.  They form the
basis for dependency graph construction and execution planning, and are immutable once
created.

Job
---

A **Job** is the executable runtime instance created from a :ref:`JobSpec <basics-jobspec>`.
The ``canary`` session constructs Job objects from resolved JobSpecs and manages their
execution.  Jobs are responsible for:

- Executing the specified command in a dedicated directory
- Managing resources during execution
- Capturing output and results
- Handling timeouts and failures
- Reporting status back to the session

See :ref:`basics-job` for the full Job API reference.

Workspace
---------

A **workspace** is the persistent storage environment for a ``canary`` project.
It includes:

- Job specifications (in ``workspace.sqlite3``)
- Session execution directories
- Result views (``TestResults/``)
- Workspace configuration (``config.yaml``)
- Temporary files and caches

``canary`` manages workspaces to ensure isolation and reproducibility across job
executions.  See :ref:`basics-workspace` for creation, inspection, and directory
layout.

Session
-------

The **session** is the central coordinator that manages a single execution run:

- Discovers and collects job definitions
- Resolves dependencies between jobs
- Constructs the execution graph
- Schedules jobs based on resources and dependencies
- Manages job execution and monitoring
- Handles failures and status tracking
- Persists results and updates the workspace database

Each ``canary run`` invocation creates a new session.  See :ref:`basics-session` for
the session lifecycle, ``session.lock`` format, and session management commands.

Resource Pool
-------------

A **resource pool** represents the available computational resources for job execution:

- CPU cores
- GPU devices
- Custom resource types (FPGAs, accelerators, etc.)

``canary`` performs resource-aware scheduling to efficiently utilize available
resources while respecting job requirements and constraints.  See
:ref:`basics-resource` for pool definition and resource specification syntax.

Dependency Graph
----------------

The **dependency graph** represents directed relationships between jobs.  It enables:

- Execution ordering based on explicit dependencies
- Failure propagation and masking of dependent jobs
- Parallel execution where dependencies allow
- Cycle detection and validation

Dependencies are declared in test files using directives and resolved during the
collection phase.  See :ref:`user-dependencies` for dependency patterns, conditions,
and groups.

Status and Result
-----------------

Each job has a **status** that tracks its execution state through two levels:

- **Category**: High-level outcome (``PASS``, ``FAIL``, ``CANCEL``, ``SKIP``)
- **Outcome**: Specific result (``SUCCESS``, ``XFAIL``, ``FAILED``, ``TIMEOUT``, etc.)

See :ref:`basics-status` for the complete status reference.

Persistence
-----------

``canary`` persists job specifications, execution results, and status to enable:

- Resuming interrupted sessions
- Querying historical results
- Generating reports and summaries
- Auditing and debugging

All persistent data is stored in ``workspace.sqlite3`` within the ``.canary/``
directory.

Reporting
---------

``canary`` provides reporting capabilities through plugins that can:

- Generate execution summaries in various formats
- Export data as JSON, JUnit XML, HTML, Markdown, etc.
- Integrate with external systems (CDash, GitLab, etc.)

See ``canary report --help`` for available reporters.

.. _basics-concepts-generators:

Plugin Architecture
-------------------

``canary``'s plugin architecture enables extensibility at multiple levels:

- **Job Generators**: Add support for new input file formats
- **Reporters**: Add new output and reporting formats
- **Scheduler Backends**: Add new execution environments (HPC, Flux, etc.)
- **Resource Backends**: Add specialized resource management

The bundled generator extensions are:

``canary_pyt``
  Python-based job definitions (``.pyt`` files).  The reference implementation
  and primary format for new test suites.

``canary_cmake``
  CMake/CTest integration (``CTestTestFile.cmake``).  See :ref:`canary-cmake`.

``canary_vvtest``
  VVTest compatibility layer (``.vvt`` files).  See :ref:`canary-vvtest`.

Plugins register under the ``canary`` `entry point group
<https://packaging.python.org/en/latest/specifications/entry-points/>`_ and
participate in the job lifecycle through well-defined hook interfaces.  See
:ref:`extending` for how to author and register plugins.
