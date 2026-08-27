.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

HPC Scheduler Extension Overview
==================================

The ``canary_hpc`` extension is a **scheduler/batching execution extension** for Canary that enables test execution on high-performance computing (HPC) systems. It replaces Canary's local test-execution phase with an HPC batching and submission workflow, allowing tests to run on HPC schedulers through `hpc_connect`.

Extension Type
--------------

**Extension type**: scheduler/batching execution extension, command provider, resource-pool provider

The ``canary_hpc`` extension:

- Provides the ``canary hpc`` command and legacy ``canary run -b ...`` options
- Uses Canary's ordinary collection, selection, job, resource, and persistence model
- Replaces local test execution with HPC batching and submission
- Batches selected Canary jobs into ``TestBatch`` objects
- Submits batches through `hpc_connect`
- Launches nested Canary executions inside allocated batch workspaces
- Does not define job file formats
- Does not replace Canary's core resource model
- Uses `hpc_connect` backend descriptions to construct topology-aware resource pools

Key Features
------------

1. **HPC Scheduler Integration**: Connects to HPC schedulers via `hpc_connect` backends
2. **Batch Execution**: Groups jobs into batches for efficient scheduler submission
3. **Resource Management**: Uses `hpc_connect` backend resources to build Canary resource pools
4. **Nested Execution**: Runs Canary inside batch workspaces with batch-local resource pools
5. **Command Integration**: Provides both ``canary hpc`` commands and legacy ``canary run -b`` options
6. **Backend Flexibility**: Supports multiple HPC backends (Slurm, PBS, Flux, shell, etc.)
7. **Batch Specification**: Configurable batching dimensions and layouts
8. **Timeout Management**: Queue and run timeouts for scheduler jobs
9. **Status Tracking**: Batch status aggregation and failure handling
10. **Debugging Support**: Batch workspaces and log files for troubleshooting

Relationship to Canary
----------------------

The ``canary_hpc`` extension builds on Canary's core functionality:

**What the extension DOES**:

- Provides HPC scheduler integration through `hpc_connect`
- Adds ``canary hpc`` subcommands and legacy batch options
- Implements batching and submission workflow
- Manages HPC resource pools and batch workspaces
- Handles nested Canary execution in batch contexts

**What the extension DOES NOT do**:

- Define job file formats or specification syntax
- Replace Canary's core resource model
- Execute jobs locally (replaces local execution with HPC submission)
- Schedule jobs directly (uses `hpc_connect` for scheduler interaction)
- Define how users request resources (uses Canary's standard resource requirements)

Relationship to hpc_connect
---------------------------

The ``canary_hpc`` extension uses `hpc_connect` as an external dependency:

- **External to Canary**: `hpc_connect` is a separate package, not part of Canary
- **Backend Provider**: `canary_hpc` uses `hpc_connect` to describe backends and submit scheduler jobs
- **Backend Access**: Uses `hpc_connect.get_backend(...)` to obtain backend instances
- **Backend Information**: Uses backend properties like `node_count`, `resource_types()`, `count_per_node()`, and `supports_dependencies()`
- **Scheduler Details**: Actual scheduler-specific behavior is provided by `hpc_connect` backends
- **No API Documentation**: This documentation does not generate or vendor `hpc_connect` API documentation

Basic Usage
-----------

The HPC extension provides several commands and options:

**Modern HPC Commands**:

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary hpc run --backend=shell --batch-spec=count=4 ./basic, python3 -m canary status -rA]
   :cwd: /examples

This example demonstrates HPC batching using the shell backend for local testing.

.. code-block:: console

   # Show HPC backend information
   python3 -m canary hpc info slurm

   # Run tests with HPC batching
   python3 -m canary hpc run --backend=slurm ./basic

   # Execute a specific batch
   python3 -m canary hpc exec --batch-id <batch-id>

   # Show batch logs
   python3 -m canary hpc log <batch-id>

**Legacy Batch Options**:

.. code-block:: console

   # Run with HPC backend using legacy options
   python3 -m canary run --hpc-backend=slurm ./tests

   # Run with batch specification
   python3 -m canary run -b backend=slurm -b spec=duration=30m ./tests

Command Integration
-------------------

The HPC extension integrates with Canary through command-line options and hooks:

- ``canary_cmdline_modifyargs``: Rewrites ``run`` to ``hpc run`` when ``hpc_backend`` is present
- ``canary_addoption``: Adds ``--hpc-backend`` and legacy batch options
- ``canary_addcommand``: Adds the ``hpc`` command
- ``canary_resource_pool_fill``: Fills HPC backend resource pool or batch-local resource pool
- ``canary_hpc_batch_runner``: Allows plugins to provide custom batch runners

Execution Flow
--------------

The HPC execution follows this workflow:

1. **Job Collection**: Canary collects and filters test jobs
2. **Batch Formation**: HPC extension groups jobs into batches
3. **Resource Allocation**: Allocates resources from HPC backend
4. **Batch Submission**: Submits batches to HPC scheduler via `hpc_connect`
5. **Nested Execution**: Runs Canary inside batch workspace
6. **Result Collection**: Gathers results from batch execution
7. **Status Aggregation**: Aggregates batch and job status

This workflow replaces Canary's local execution with HPC batching and submission.

Backend Support
---------------

The HPC extension supports multiple scheduler backends through `hpc_connect`:

- **Slurm**: SLURM workload manager
- **PBS**: Portable Batch System
- **Flux**: Flux Framework
- **Shell**: Local shell execution for testing
- **Other**: Any backend supported by `hpc_connect`

Backend Configuration
---------------------

Backends can be configured via:

- Command line: ``--backend=slurm``
- Environment variable: ``CANARY_HPC_BACKEND``
- Configuration files: HPC-specific configuration

Resource Pool Behavior
----------------------

In HPC mode, resource pool behavior differs from local execution:

- Resource pool overrides are rejected (``-r``, ``--resource-pool-file``, ``--oversubscribe``)
- Users configure resources in `hpc_connect` backend, not through Canary overrides
- ``fill_hpc_resource_pool()`` builds topology-aware resource pool from backend
- Generated pool has ``allow_multinode: true`` with virtual/backend-local node IDs
- Batch execution uses ``fill_batch_resource_pool()`` to load batch-local resource pool

This ensures consistent resource management across HPC environments.

Batch Specification
-------------------

The HPC extension supports configurable batching through batch specifications:

- **Layout**: ``flat`` or ``atomic`` batch organization
- **Nodes**: ``same`` or ``any`` node count policy
- **Count**: Number of batches (``auto``, ``max``, or specific count)
- **Duration**: Target batch duration
- **Workers**: Number of workers per batch

These specifications control how jobs are grouped into batches for submission.

Status and Failure Handling
---------------------------

The HPC extension provides comprehensive status tracking:

- Batch status aggregation from child jobs
- Preflight resource validation before submission
- Failure handling for incomplete or cancelled jobs
- Status propagation from batch to individual jobs
- Debugging information through batch workspaces and logs

This enables effective monitoring and troubleshooting of HPC executions.

Debugging and Diagnostics
--------------------------

The HPC extension provides debugging support through:

- Batch workspaces with metadata and logs
- Resource pool files for inspection
- Configuration snapshots for analysis
- Status commands for monitoring
- Log commands for troubleshooting

These features help diagnose and resolve HPC execution issues.

Limitations and Constraints
---------------------------

The HPC extension has several important limitations:

- Requires configured `hpc_connect` backend
- Backend resource definitions drive Canary's HPC resource pool
- Canary resource pool overrides rejected in HPC mode
- Scheduler-specific behavior delegated to `hpc_connect`
- Queue/run timeouts can cancel scheduler jobs
- Some batching combinations unsupported (e.g., duration-targeted atomic batching)

These limitations should be considered when planning HPC test execution.