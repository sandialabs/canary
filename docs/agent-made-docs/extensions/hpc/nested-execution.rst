.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Nested Execution
================

The ``canary_hpc`` extension uses a nested execution model where Canary runs inside batch workspaces. This enables HPC batch execution while maintaining Canary's test execution framework and resource management.

Nested Execution Model
----------------------

**Outer Execution** (Submission Host):

- ``canary hpc run`` command
- Batch formation and submission
- Resource pool management
- Status monitoring and aggregation

**Inner Execution** (Batch Workspace):

- ``canary hpc exec`` command
- Batch-local resource pool
- Job execution with allocated resources
- Result generation and collection

**Communication**:

- Batch workspace contains metadata and configuration
- ``resource_pool.json`` defines batch-local resources
- ``batch.lock`` records batch state
- Results copied back to submission host

Nested Execution Flow
---------------------

1. **Batch Submission**:
   - Outer execution creates batch workspace
   - Batch submitted to HPC scheduler
   - Input script prepared for nested execution

2. **Scheduler Job Start**:
   - Scheduler allocates resources
   - Scheduler starts job execution
   - Input script executed

3. **Nested Canary Invocation**:
   - ``python -m canary -C <workspace> hpc exec``
   - Batch workspace path passed via ``-C`` option
   - Batch ID and backend specified

4. **Batch Execution**:
   - Nested Canary loads batch workspace
   - Batch-local resource pool loaded
   - Jobs selected and filtered
   - Jobs executed with batch resources

5. **Result Collection**:
   - Job results saved to workspace
   - Output files generated
   - Status updated
   - Results copied back to submission host

Nested Execution Command
------------------------

**Command Structure**:

.. code-block:: console

   python -m canary -C <batch-workspace> hpc exec \
     --batch-id=<batch-id> \
     --backend=<backend> \
     --workspace=<batch-workspace>

**Components**:

- ``-C <batch-workspace>``: Canary configuration directory
- ``hpc exec``: HPC execution subcommand
- ``--batch-id``: Batch identifier
- ``--backend``: HPC backend name
- ``--workspace``: Batch workspace path

**Example**:

.. code-block:: console

   python -m canary -C /path/to/workspace hpc exec \
     --batch-id=abc1234 \
     --backend=slurm \
     --workspace=/path/to/workspace

Nested Execution Implementation
--------------------------------

**CanaryHPCExecutor**:

The nested executor handles batch execution:

1. **Workspace Loading**:
   - Loads parent workspace
   - Loads batch workspace
   - Loads batch configuration

2. **Job Selection**:
   - Selects jobs in batch
   - Masks jobs not in batch
   - Validates job requirements

3. **Resource Management**:
   - Loads batch-local resource pool
   - Validates resource allocation
   - Provides resources to jobs

4. **Execution**:
   - Calls ``workspace.run(..., only="all")``
   - Executes only jobs in batch
   - Respects batch constraints

**Implementation**:

.. code-block:: python

   # From executor.py
   class CanaryHPCExecutor:
       def __call__(self, batch, queue, **kwargs):
           # Load batch workspace
           workspace = ExecutionSpace.from_path(batch.workspace)

           # Load configuration
           config = load_config(workspace)

           # Select jobs in batch
           jobs = select_batch_jobs(batch, workspace)

           # Execute jobs
           workspace.run(jobs, only="all", queue=queue)

Job Selection in Nested Execution
----------------------------------

**Batch Job Selection**:

- Only jobs in the batch are executed
- Jobs not in batch are masked
- Batch constraints enforced
- Resource requirements validated

**Selection Logic**:

.. code-block:: python

   def select_batch_jobs(batch, workspace):
       # Get all jobs from workspace
       all_jobs = workspace.jobs

       # Filter to jobs in batch
       batch_jobs = [job for job in all_jobs if job.id in batch.jobs]

       # Mask jobs not in batch
       for job in all_jobs:
           if job.id not in batch.jobs:
               job.mask = Mask.masked("Not in batch")

       return batch_jobs

Resource Management in Nested Execution
----------------------------------------

**Batch-Local Resource Pool**:

- Loaded from ``resource_pool.json``
- Provides resources to nested execution
- Validates job requirements
- Enforces batch constraints

**Resource Pool Loading**:

.. code-block:: python

   def load_batch_resource_pool(workspace):
       # Read resource pool file
       with open(workspace / "resource_pool.json") as f:
           data = json.load(f)

       # Create resource pool
       pool = ResourcePool.from_dict(data["resource_pool"])

       # Validate resources
       validate_resources(pool, workspace.jobs)

       return pool

Status Handling in Nested Execution
------------------------------------

**Batch Status**:

- ``TestBatch`` status derived from child jobs
- Base status for batch itself
- Display behavior from child jobs
- Success only when all child jobs pass

**Status Propagation**:

.. code-block:: python

   def compute_batch_status(batch):
       # Check child job status
       child_statuses = [job.status for job in batch.jobs]

       # Compute batch status
       if all(status == "SUCCESS" for status in child_statuses):
           return "SUCCESS"
       elif any(status == "FAILED" for status in child_statuses):
           return "FAILED"
       else:
           return "RUNNING"

Failure Handling in Nested Execution
-------------------------------------

**Preflight Failures**:

- Resource validation before execution
- Jobs marked ``BROKEN`` on failure
- Specific failure reasons provided
- Prevents wasted execution

**Execution Failures**:

- Incomplete jobs marked ``BROKEN``
- Jobs still running marked ``CANCELLED``
- Batch status reflects failures
- Detailed error information captured

**Failure Examples**:

.. code-block:: console

   # Job with insufficient resources
   python3 -m canary hpc run --backend=slurm -p "cpus=100" ./basic

   # Job with invalid configuration
   python3 -m canary hpc run --backend=slurm --batch-spec=invalid ./basic

Nested Execution Debugging
--------------------------

**Verbose Logging**:

.. code-block:: console

   # Nested execution with verbose logging
   python3 -m canary hpc run --backend=slurm --verbose ./basic

   # Check nested execution logs
   cat .canary/cache/canary-hpc/batches/abc1234/canary-out.txt

**Workspace Inspection**:

.. code-block:: console

   # Inspect batch workspace
   ls .canary/cache/canary-hpc/batches/abc1234/

   # Check batch configuration
   cat .canary/cache/canary-hpc/batches/abc1234/config.json

**Status Monitoring**:

.. code-block:: console

   # Check batch status
   python3 -m canary hpc log abc1234

   # Monitor nested execution
   python3 -m canary hpc run --backend=slurm --verbose ./basic

Nested Execution Examples
-------------------------

**Simple Nested Execution**:

.. code-block:: console

   # Basic nested execution
   python3 -m canary hpc run --backend=slurm ./basic

**Nested with Batch Specification**:

.. code-block:: console

   # Nested execution with batch spec
   python3 -m canary hpc run --backend=slurm --batch-spec=count=4 ./basic

**Nested with Resource Requirements**:

.. code-block:: console

   # Nested execution with resources
   python3 -m canary hpc run --backend=slurm -p "nodes=2,cpus=8" ./basic

**Nested with Timeout Configuration**:

.. code-block:: console

   # Nested execution with timeouts
   python3 -m canary hpc run --backend=slurm --timeout queue=30m,run=2h ./basic

Nested Execution Limitations
----------------------------

1. **Complexity**: Nested execution adds debugging complexity
2. **Resource Isolation**: Batch resources isolated from parent
3. **Status Propagation**: Status must be propagated correctly
4. **Failure Handling**: Complex failure scenarios possible
5. **Workspace Management**: Workspace cleanup and retention
6. **Configuration**: Nested configuration must match batch requirements

Nested Execution Best Practices
--------------------------------

1. **Workspace Inspection**: Regularly inspect batch workspaces
2. **Logging**: Use verbose logging for nested execution
3. **Validation**: Validate batch configuration before submission
4. **Monitoring**: Monitor nested execution status
5. **Debugging**: Use workspace files for troubleshooting
6. **Documentation**: Document nested execution behavior
7. **Testing**: Test nested execution with simple batches first