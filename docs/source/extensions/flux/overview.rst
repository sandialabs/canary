.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Flux Extension Overview
=======================

The ``canary_flux`` extension is a **Flux Framework execution extension** for Canary that enables direct test execution through Flux allocations. Unlike the HPC extension which uses batch-oriented workflows, ``canary_flux`` runs individual Canary jobs directly inside a Flux allocation, providing fine-grained control and efficient resource utilization.

Extension Type
--------------

**Extension type**: scheduler execution extension, command provider, resource-pool provider

The ``canary_flux`` extension:

- Provides the ``canary flux`` command with ``run`` and ``exec`` subcommands
- Uses Canary's ordinary collection, selection, job, resource, and persistence model
- Replaces local test execution with direct Flux allocation and submission
- Runs each Canary job as an individual Flux JobSpecV1 inside an active allocation
- Uses `hpc_connect` Flux backend for allocation management
- Provides detailed timing and resource metadata for Flux executions
- Does not use batching (each job runs individually in the allocation)

Key Features
------------

1. **Direct Flux Integration**: Connects to Flux Framework via `hpc_connect` Flux backend
2. **Fine-Grained Execution**: Runs each Canary job as an individual Flux job within an allocation
3. **Resource Management**: Uses `hpc_connect` backend resources to build Canary resource pools
4. **Nested Execution**: Runs Canary inside Flux allocation with Flux-local resource assignment
5. **Comprehensive Timing**: Tracks allocation, submission, and execution phases separately
6. **GPU/CPU Assignment**: Automatic resource assignment from Flux environment variables
7. **Live Reporting**: Real-time progress monitoring during Flux execution
8. **Timeout Management**: Queue and allocation timeouts for Flux jobs
9. **Status Tracking**: Detailed job status and failure handling
10. **Debugging Support**: Flux workspaces, logs, and metadata for troubleshooting

Relationship to Canary
----------------------

The ``canary_flux`` extension builds on Canary's core functionality:

**What the extension DOES**:

- Provides Flux Framework integration through `hpc_connect`
- Adds ``canary flux`` subcommands for direct Flux execution
- Implements allocation and submission workflow for individual jobs
- Manages Flux resource pools and job workspaces
- Handles nested Canary execution in Flux contexts
- Tracks detailed timing metrics for allocation and job phases

**What the extension DOES NOT do**:

- Define job file formats or specification syntax
- Replace Canary's core resource model
- Execute jobs locally (replaces local execution with Flux submission)
- Use batching (runs jobs individually within an allocation)
- Schedule jobs directly (uses `hpc_connect` for Flux interaction)
- Define how users request resources (uses Canary's standard resource requirements)

Relationship to hpc_connect
---------------------------

The ``canary_flux`` extension uses `hpc_connect` as an external dependency:

- **External to Canary**: `hpc_connect` is a separate package, not part of Canary
- **Backend Provider**: `canary_flux` uses `hpc_connect` to manage Flux allocations and submit jobs
- **Backend Access**: Uses `hpc_connect.get_backend("flux")` to obtain Flux backend instances
- **Backend Information**: Uses backend properties like `node_count`, `resource_types()`, and `count_per_node()`
- **Flux Details**: Actual Flux-specific behavior is provided by `hpc_connect` Flux backend
- **No API Documentation**: This documentation does not generate or vendor `hpc_connect` API documentation

Relationship to canary_hpc
---------------------------

The ``canary_flux`` extension differs from ``canary_hpc`` in several key ways:

**canary_flux**:

- Designed for direct Flux Framework integration
- Runs individual jobs within a single Flux allocation
- No batching layer (each Canary job = one Flux job)
- Fine-grained resource control per job
- Lower overhead for small-scale Flux executions
- Uses ``canary flux run`` command

**canary_hpc with Flux backend**:

- Designed for general HPC scheduler batching
- Groups jobs into batches before submission
- Batching layer adds flexibility for large-scale executions
- Can use Flux as one of many backends
- Higher overhead due to batching infrastructure
- Uses ``canary hpc run --backend=flux`` command

Use ``canary_flux`` when you need direct, fine-grained Flux execution. Use ``canary_hpc`` when you need batching capabilities or multi-backend support.

Basic Usage
-----------

The Flux extension provides commands for direct Flux execution:

**Modern Flux Commands**:

.. code-block:: console

   # Run tests through Flux allocation
   python3 -m canary flux run ./basic

   # Run with specific node count
   python3 -m canary flux run --nodes 4 ./basic

   # Run with allocation arguments
   python3 -m canary flux run --alloc-arg="--time-limit=60" ./basic

   # Run with submission arguments
   python3 -m canary flux run --submit-arg="--queue=debug" ./basic

Command Integration
-------------------

The Flux extension integrates with Canary through command-line subcommands and hooks:

- ``canary_addcommand``: Adds the ``flux`` command
- ``canary_resource_pool_fill``: Fills Flux backend resource pool
- ``canary_runtests``: Implements Flux allocation and execution workflow
- ``canary_runtest_finish``: Captures environment for debugging

Execution Flow
--------------

The Flux execution follows this workflow:

1. **Job Collection**: Canary collects and filters test jobs
2. **Resource Pool Creation**: Builds resource pool from Flux backend
3. **Allocation Request**: Requests Flux allocation with specified node count
4. **Allocation Grant**: Flux allocation becomes active
5. **Job Submission**: Submits individual Canary jobs as Flux jobs within allocation
6. **Nested Execution**: Runs each job via ``canary flux exec`` inside allocation
7. **Result Collection**: Gathers results from Flux job execution
8. **Allocation Cleanup**: Closes Flux allocation when complete

This workflow provides direct, fine-grained control over Flux execution without batching.

Backend Support
---------------

The Flux extension specifically supports the Flux Framework backend through `hpc_connect`:

- **Flux**: Flux Framework (primary backend)
- **Other**: Any Flux-compatible backend supported by `hpc_connect`

The extension uses the Flux backend's capabilities for allocation management and job submission.

Resource Pool Behavior
----------------------

In Flux mode, resource pool behavior differs from local execution:

- Resource pool overrides are rejected (``-r``, ``--resource-pool-file``, ``--oversubscribe``)
- Users configure resources in `hpc_connect` Flux backend, not through Canary overrides
- ``canary_resource_pool_fill`` builds topology-aware resource pool from Flux backend
- Generated pool has ``allow_multinode: true`` with virtual/backend-local node IDs
- Resource counts come from backend's ``resource_types()`` and ``count_per_node()`` methods
- Defaults to 1 CPU per node if backend doesn't report CPU count

This ensures consistent resource management across Flux environments.

Resource Assignment
-------------------

The Flux extension provides automatic resource assignment from Flux environment:

- **GPU Assignment**: Uses ``CUDA_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, ``HIP_VISIBLE_DEVICES``, or ``GPU_DEVICE_ORDINAL``
- **CPU Assignment**: Creates placeholder CPU resources based on job requirements
- **Metadata**: Records Flux job ID and URI in job metadata
- **Environment Capture**: Saves full environment to ``env.json`` for debugging

This automatic assignment ensures jobs have access to allocated resources.

Status and Failure Handling
---------------------------

The Flux extension provides comprehensive status tracking:

- Individual job status from nested ``canary flux exec`` execution
- Flux job submission failure detection
- Timeout handling for queue and allocation phases
- Status propagation from child jobs to parent
- Debugging information through Flux workspaces and logs

This enables effective monitoring and troubleshooting of Flux executions.

Debugging and Diagnostics
--------------------------

The Flux extension provides debugging support through:

- Flux submit workspaces with metadata and logs
- Resource pool files for inspection
- Configuration snapshots for analysis
- Environment capture in ``env.json`` files
- Process info in ``procinfo.json`` files
- Timing metrics in job measurements

These features help diagnose and resolve Flux execution issues.

Limitations and Constraints
---------------------------

The Flux extension has several important limitations:

- Requires configured `hpc_connect` Flux backend
- Backend resource definitions drive Canary's Flux resource pool
- Canary resource pool overrides rejected in Flux mode
- Flux-specific behavior delegated to `hpc_connect`
- Queue/allocation timeouts can cancel Flux jobs
- No batching (each job runs individually)
- All jobs run within single allocation lifetime

These limitations should be considered when planning Flux test execution.

Timing and Overhead Tracking
-----------------------------

The Flux extension tracks comprehensive timing metrics:

**Allocation Phase**:

- ``allocation_requested_at``: When allocation was requested
- ``allocation_granted_at``: When allocation became active
- ``allocation_wait_seconds``: Time spent waiting for allocation

**JobspecV1 Phase**:

- ``jobspec_submitted_at``: When job was submitted to Flux
- ``flux_started_at``: When Flux job started
- ``inner_opened_at``: When inner Canary job opened
- ``inner_started_at``: When inner Canary job started
- ``inner_stopped_at``: When inner Canary job stopped
- ``inner_finished_at``: When inner Canary job finished
- ``flux_finished_at``: When Flux job completed

**Duration Metrics**:

- ``allocation_request_to_jobspec_submit_seconds``: Pre-submit delay
- ``jobspec_submit_to_flux_start_seconds``: Flux scheduling delay
- ``flux_start_to_inner_finish_seconds``: Total Flux execution time
- ``inner_finish_to_flux_return_seconds``: Return overhead
- ``flux_jobspec_total_seconds``: Total Flux job time
- ``launch_seconds``: Overhead before inner job opens
- ``return_seconds``: Overhead after inner job finishes

These metrics enable detailed performance analysis and overhead identification.

When to Use canary_flux
-----------------------

Use ``canary_flux`` when:

- You need direct Flux Framework integration
- You want fine-grained control over individual jobs
- You're working with Flux allocations directly
- You need detailed timing metrics for Flux overhead
- You prefer individual job submission over batching
- You're debugging Flux execution issues
- You need automatic GPU/CPU assignment from Flux environment

Use ``canary_hpc`` with Flux backend when:

- You need batching capabilities
- You want to run multiple backends
- You need large-scale job organization
- You're migrating from other HPC schedulers
- You need batch-level status aggregation

The ``canary_flux`` extension integrates with the `Flux Framework <https://flux-framework.org>`_ for HPC job execution.
