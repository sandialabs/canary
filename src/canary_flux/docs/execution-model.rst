.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Execution Model
===============

The ``canary_flux`` extension implements a direct execution model that runs individual Canary jobs as Flux JobSpecV1 instances within an active Flux allocation. This model provides fine-grained control and efficient resource utilization.

Execution Phases
----------------

The Flux execution model consists of several distinct phases:

1. **Collection Phase**
   - Canary collects test specifications from provided paths
   - Filters and selects jobs based on command-line options
   - Creates Canary Job objects with resource requirements
   - Standard Canary collection mechanism (unchanged)

2. **Resource Pool Phase**
   - ``canary_resource_pool_fill`` hook creates Flux resource pool
   - Queries `hpc_connect` Flux backend for node count and resources
   - Builds topology-aware resource pool with virtual node IDs
   - Sets ``allow_multinode: true`` for Flux execution
   - Resource counts come from backend's ``resource_types()`` and ``count_per_node()``

3. **Allocation Phase**
   - Requests Flux allocation with specified node count
   - Waits for allocation to be granted (with queue timeout)
   - Opens FluxAllocation context for job submission
   - Records allocation timing metrics

4. **Submission Phase**
   - Creates FluxJob wrappers for each Canary job
   - Checks job readiness and dependencies
   - Submits ready jobs as Flux JobSpecV1 instances
   - Tracks submission status and timing
   - Limits concurrent submissions based on ``--workers`` option

5. **Execution Phase**
   - Flux scheduler starts each job in allocation
   - Calls ``canary flux exec`` for each job
   - Runs nested Canary execution inside Flux context
   - Assigns resources from Flux environment
   - Captures job output and status

6. **Completion Phase**
   - Collects results from completed jobs
   - Updates job status and measurements
   - Records Flux timing and overhead metrics
   - Closes Flux allocation
   - Persists results to workspace database

Resource Management
-------------------

Resource Pool Creation
~~~~~~~~~~~~~~~~~~~~~~

The Flux extension creates resource pools from the `hpc_connect` backend:

**Backend Query**:
- Calls ``backend.node_count`` to determine available nodes
- Calls ``backend.resource_types()`` to discover resource types
- Calls ``backend.count_per_node(rtype)`` for each resource type
- Handles both singular and plural resource type names

**Resource Types**:
- ``cpus``: CPU cores (defaults to 1 if not reported)
- ``gpus``: GPU devices (defaults to 0 if not reported)
- Other resource types reported by backend

**Pool Structure**:
- Virtual node IDs: ``0``, ``1``, ``2``, ... ``N-1``
- Each node has resources based on backend counts
- ``allow_multinode: true`` for multi-node jobs
- Additional properties include backend name and source

Resource Assignment
~~~~~~~~~~~~~~~~~~~

Jobs receive resources through automatic assignment:

**GPU Assignment**:
- Reads ``CUDA_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, ``HIP_VISIBLE_DEVICES``, or ``GPU_DEVICE_ORDINAL``
- Creates GPU resource entries with Flux job ID
- Sets ``CANARY_GPU_IDS`` variable for job use

**CPU Assignment**:
- Creates placeholder CPU resources based on job requirements
- Assigns CPU IDs with Flux job ID
- Provides basic CPU resource information

**Metadata**:
- Records ``flux_jobid`` from ``FLUX_JOB_ID`` environment variable
- Records ``flux_uri`` from ``FLUX_URI`` environment variable
- Marks resources as coming from ``canary_flux`` source

Job Submission
--------------

The Flux extension submits jobs through the `hpc_connect` submission manager:

**JobspecV1 Creation**:
- Creates ``hpc_connect.JobSpec`` for each job
- Sets name to ``canary.<job-id-prefix>``
- Configures CPU, GPU, and node requirements
- Sets time limit from job's total timeout
- Configures environment variables for nested execution
- Sets workspace to Flux submit workspace

**Command Generation**:
- Uses ``python3 -m canary -C <workspace> flux exec --session <session> <job-id>``
- Adds ``-d`` flag if debug mode enabled
- Sets ``CANARY_LEVEL`` to prevent infinite nesting
- Disables live reporting and keyboard interrupts
- Passes serialized configuration

**Environment Setup**:
- ``CANARY_LEVEL``: Incremented to track nesting depth
- ``CANARY_LIVE``: Set to ``0`` to disable live console
- ``CANARY_DISABLE_KB``: Set to ``1`` to disable keyboard interrupts
- ``CANARY_FLUX_DIRECT_JOB``: Set to job ID
- ``CANARY_FLUX_SUBMIT_WORKSPACE``: Set to submit workspace path
- ``CANARY_CONFIG_ENV_CFG64``: Serialized Canary configuration

Concurrency Control
-------------------

The Flux extension manages concurrent job submission:

**Worker Limit**:
- ``--workers N`` limits maximum concurrent submissions
- Default (unlimited) submits all ready jobs immediately
- Worker limit applies to submitted (not running) jobs

**Ready Job Selection**:
- Jobs sorted by cost (high-cost first)
- Only ready jobs (dependencies satisfied) are submitted
- Failed dependency jobs marked as BLOCKED

**Submission Loop**:
- Submits ready jobs until worker limit reached
- Polls for finished jobs to free worker slots
- Refreshes running jobs to update status
- Finalizes blocked jobs when no progress possible

Timeout Management
------------------

The Flux extension manages several timeout types:

**Queue Timeout**:
- ``--timeout type=queue,T`` or default 1200 seconds
- Maximum time to wait for Flux allocation to be granted
- Also applies to individual job submission wait time

**Allocation Timeout**:
- ``--timeout type=allocation,T`` or default 3600 seconds
- Walltime requested for outer Flux allocation
- Converted to minutes for ``--time-limit`` argument
- Can be specified via ``--alloc-arg="--time-limit=..."``

**Session Timeout**:
- ``--timeout type=session,T`` as fallback
- Used if no allocation timeout specified
- Provides default walltime for allocation

**Job Timeout**:
- Each job's ``total_timeout()`` used for JobspecV1
- Controls maximum runtime for individual jobs
- Independent of allocation walltime

Timing and Metrics
------------------

The Flux extension tracks comprehensive timing metrics:

**Allocation Timing**:
- ``allocation_requested_at``: When allocation request started
- ``allocation_granted_at``: When allocation became active
- ``allocation_wait_seconds``: Duration of allocation wait

**JobspecV1 Timing**:
- ``jobspec_submitted_at``: When job submitted to Flux
- ``flux_started_at``: When Flux job started (from callback)
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

**Overhead Metrics**:
- ``launch_seconds``: Overhead before inner job opens
- ``return_seconds``: Overhead after inner job finishes
- ``return_after_inner_stop_seconds``: Return overhead using stop boundary
- ``total_external_seconds``: Sum of launch and return overheads

**Inner Canary Timing**:
- ``inner_total_seconds``: Total inner job time
- ``inner_pending_seconds``: Inner pending phase
- ``inner_staging_seconds``: Inner staging phase
- ``inner_command_seconds``: Inner command execution
- ``inner_finishing_seconds``: Inner finishing phase

These metrics are stored in job measurements under the ``flux`` key.

Failure Handling
----------------

The Flux extension handles various failure scenarios:

**Allocation Failure**:
- If allocation request times out (queue timeout)
- If allocation cannot be granted
- Marked as allocation failed in logs

**Submission Failure**:
- If job submission to Flux fails
- Job marked with ERROR status and reason
- Job persisted immediately (no child execution)

**Execution Failure**:
- If Flux job returns non-zero exit code
- If Flux job raises exception
- Job status updated based on exit code

**Dependency Failure**:
- If job dependencies fail
- Job marked as BLOCKED
- Job finalized without submission

**Timeout Failure**:
- If session time limit exceeded
- Remaining jobs cancelled
- Allocation closed

**Stuck Jobs**:
- If jobs never become ready
- Marked as BROKEN after all Flux jobs complete
- Reason: "Job never became ready and no Flux jobs remain running"

Status Propagation
------------------

Job status flows through several layers:

1. **Inner Canary Execution**: ``canary flux exec`` sets authoritative status
2. **Flux Job Result**: Exit code and exceptions from Flux execution
3. **Parent Aggregation**: Parent process aggregates child status
4. **Final Status**: Combination of inner status and Flux result

**Status Priority**:
- Inner Canary status (if set) takes precedence
- Flux exit code used if inner status unset
- Flux exceptions override exit code
- Submission failures marked immediately

Workspace Management
--------------------

The Flux extension manages several workspace types:

**Submit Workspace**:
- Location: ``<cache_dir>/canary-flux/<session>/jobs/<job-id>``
- Contains: Flux output/error files, proc_info.json
- Purpose: Flux job submission and output capture

**Job Workspace**:
- Location: Standard Canary job workspace
- Contains: Test files, resources, env.json, results
- Purpose: Individual job execution context

**Session Workspace**:
- Location: Standard Canary session workspace
- Contains: Database, views, metadata
- Purpose: Session-level persistence and results

**Cache Directory**:
- Location: ``<workspace>.cache_dir``
- Contains: Flux submit workspaces, temporary files
- Purpose: Temporary storage during Flux execution

Debugging Artifacts
-------------------

The Flux extension creates several debugging artifacts:

**env.json**:
- Location: Job workspace
- Contents: Full environment dictionary at job finish
- Purpose: Debugging environment issues

**procinfo.json**:
- Location: Submit workspace
- Contents: Flux process info, job metadata
- Purpose: Debugging Flux execution issues

**flux.out / flux.err**:
- Location: Submit workspace
- Contents: Flux job stdout/stderr
- Purpose: Debugging job output

**testcase.lock**:
- Location: Job workspace
- Contents: Authoritative job status and measurements
- Purpose: Status persistence and parent-child communication

Execution Flow Diagram
----------------------

.. code-block:: text

   User
    |
    v
   canary flux run --> Collection --> Resource Pool --> Allocation Request
    |                                                             |
    |                                                             v
    |                                                        Allocation Granted
    |                                                             |
    |                                                             v
    |                                                        Job Submission
    |                                                             |
    |                                                             v
    +--------------------------------> Flux Scheduler --> Job Start
    |                                                             |
    |                                                             v
    |                                                       canary flux exec
    |                                                             |
    |                                                             v
    |                                                       Job Execution
    |                                                             |
    |                                                             v
    +--------------------------------> Result Collection --> Status Update
    |                                                             |
    |                                                             v
    |                                                        Allocation Close
    |                                                             |
    |                                                             v
    |                                                       Session Complete
    |
    v
   Results

This flow shows the direct relationship between user command, Flux allocation, and individual job execution.

Comparison with HPC Extension
------------------------------

The Flux extension's execution model differs from the HPC extension:

**Flux Extension (canary_flux)**:
- Direct Flux allocation management
- Individual job submission (no batching)
- Fine-grained resource control
- Lower overhead per job
- Simpler execution flow
- Direct status propagation

**HPC Extension (canary_hpc)**:
- Batching layer between Canary and scheduler
- Jobs grouped into batches
- Batch-level resource management
- Higher overhead due to batching
- More complex execution flow
- Batch status aggregation

Use Flux extension for direct, fine-grained Flux execution. Use HPC extension for batching and multi-backend support.
