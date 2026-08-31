.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Flux Job Lifecycle
==================

The ``canary_flux`` extension manages individual Canary jobs as Flux JobSpecV1 instances, providing fine-grained control over job execution within Flux allocations.

Job Lifecycle Phases
====================

**Key Phases**:

1. **Job Creation**: Canary job object creation and initialization
2. **Resource Assignment**: Flux resource assignment from environment
3. **JobspecV1 Submission**: Submission to Flux scheduler
4. **Flux Execution**: Execution within Flux allocation
5. **Status Propagation**: Result collection and status update
6. **Lifecycle Completion**: Finalization and persistence

Job Creation
------------

**Job Object Creation**:
- Canary jobs created from specifications
- Job ID, name, and requirements set
- Dependencies and resource requirements configured

**FluxJob Wrapper**:
- ``FluxJob`` wrapper created for each Canary job
- Tracks Flux-specific lifecycle and timing
- Maintains reference to inner Canary job

Resource Assignment
-------------------

**GPU Assignment**:
- Reads ``CUDA_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, ``HIP_VISIBLE_DEVICES``, or ``GPU_DEVICE_ORDINAL``
- Creates GPU resource entries with Flux job ID
- Sets ``CANARY_GPU_IDS`` variable for job use

**CPU Assignment**:
- Creates placeholder CPU resources based on job requirements
- Assigns CPU IDs with Flux job ID
- Provides basic CPU resource information

JobspecV1 Submission
--------------------

**JobspecV1 Creation**:
- Creates ``hpc_connect.JobSpec`` for each job
- Sets name to ``canary.<job-id-prefix>``
- Configures CPU, GPU, and node requirements
- Sets time limit from job's total timeout

**Command Generation**:
- Uses ``python3 -m canary -C <workspace> flux exec --session <session> <job-id>``
- Adds ``-d`` flag if debug mode enabled
- Sets ``CANARY_LEVEL`` to prevent infinite nesting

**Environment Setup**:
- ``CANARY_LEVEL``: Incremented to track nesting depth
- ``CANARY_LIVE``: Set to ``0`` to disable live console
- ``CANARY_DISABLE_KB``: Set to ``1`` to disable keyboard interrupts
- ``CANARY_FLUX_DIRECT_JOB``: Set to job ID

Flux Execution
--------------

**Submission Process**:
- Jobs submitted through ``submission_manager()``
- Submission limited by ``--workers`` option
- Ready jobs sorted by cost (high-cost first)

**Execution Flow**:
- Flux scheduler starts each job in allocation
- Calls ``canary flux exec`` for each job
- Runs nested Canary execution inside Flux context

Status Propagation
------------------

**Status Priority**:
1. Inner Canary status (if set) takes precedence
2. Flux exit code used if inner status unset
3. Flux exceptions override exit code
4. Submission failures marked immediately

**Status Categories**:
- ``SUCCESS``: Job completed successfully
- ``FAILED``: Job failed during execution
- ``ERROR``: Flux submission or execution error
- ``TIMEOUT``: Job exceeded timeout
- ``BLOCKED``: Job dependencies failed
- ``BROKEN``: Job never became ready

Lifecycle Completion
--------------------

**Result Collection**:
- Results gathered from completed jobs
- Job status and measurements updated
- Flux timing and overhead metrics recorded

**Persistence**:
- Job results persisted to workspace database
- Status written to ``testcase.lock``
- Measurements stored in job workspace

Job State Management
====================

**State Transitions**:

.. code-block:: text

   PENDING → SUBMITTED → RUNNING → STOPPED → FINISHED
                     ↓
                  FAILED/ERROR

**State Methods**:
- ``is_ready()``: Check if job ready to run
- ``is_runnable()``: Check if job can be executed
- ``is_done()``: Check if job completed
- ``refresh_readiness()``: Update readiness state

Job Lifecycle Timing
====================

**Allocation Timing**:
- ``allocation_requested_at``: When allocation was requested
- ``allocation_granted_at``: When allocation became active
- ``allocation_wait_seconds``: Time spent waiting for allocation

**JobspecV1 Timing**:
- ``jobspec_submitted_at``: When job was submitted to Flux
- ``flux_started_at``: When Flux job started
- ``inner_opened_at``: When inner Canary job opened
- ``inner_finished_at``: When inner Canary job finished
- ``flux_finished_at``: When Flux job completed

**Duration Metrics**:
- ``allocation_request_to_jobspec_submit_seconds``: Pre-submit delay
- ``jobspec_submit_to_flux_start_seconds``: Flux scheduling delay
- ``flux_start_to_inner_finish_seconds``: Total Flux execution time
- ``flux_jobspec_total_seconds``: Total Flux job time

**Overhead Metrics**:
- ``launch_seconds``: Overhead before inner job opens
- ``return_seconds``: Overhead after inner job finishes
- ``total_external_seconds``: Sum of launch and return overheads

Lifecycle Management
====================

**Concurrency Control**:
- ``--workers N`` limits maximum concurrent submissions
- Default (unlimited) submits all ready jobs immediately

**Dependency Management**:
- Jobs sorted by cost (high-cost first)
- Only ready jobs (dependencies satisfied) are submitted
- Failed dependency jobs marked as BLOCKED

**Timeout Management**:
- Queue timeout for allocation and submission
- Allocation timeout for Flux walltime
- Job timeout for individual execution
- Session timeout as fallback

Job Lifecycle Examples
======================

Basic Job Lifecycle
-------------------

.. code-block:: console

   # Run with Flux allocation
   python3 -m canary flux run ./basic

Job with Dependencies
---------------------

.. code-block:: console

   # Run with dependency management
   python3 -m canary flux run ./dependent-tests

Job with Timeouts
-----------------

.. code-block:: console

   # Run with timeout configuration
   python3 -m canary flux run --timeout queue=30m,allocation=2h ./basic

Job Lifecycle Comparison
========================

**Flux Extension (canary_flux)**:
- Direct Flux job lifecycle management
- Individual job submission and execution
- Fine-grained lifecycle control
- Detailed timing and status tracking

**HPC Extension (canary_hpc)**:
- Batch-level lifecycle management
- Jobs grouped into batches
- Batch status aggregation
- More complex lifecycle flow

