.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Batch Specification
===================

The ``canary_hpc`` extension uses batch specifications to control how jobs are grouped into batches for HPC scheduler submission. Batch specifications define the batching strategy, resource constraints, and execution parameters.

Batch Specification Syntax
--------------------------

Batch specifications use a key-value syntax to configure batching behavior:

.. code-block:: console

   --batch-spec="KEY1=VALUE1,KEY2=VALUE2,..."

**Syntax Rules**:

- Comma-separated key-value pairs
- No spaces around equals signs
- Values can be quoted if needed
- Order does not matter

Batch Specification Options
---------------------------

Layout
~~~~~~

**Option**: ``layout``

**Values**: ``flat`` or ``atomic``

**Default**: ``flat``

**Description**:

- ``flat``: Jobs within a batch do not depend on each other, but batches may depend on other batches
- ``atomic``: Dependency-connected components are kept together; batches do not depend on other batches

**Examples**:

.. code-block:: console

   --batch-spec=layout=flat
   --batch-spec=layout=atomic

Node Policy
~~~~~~~~~~~

**Option**: ``nodes``

**Values**: ``same`` or ``any``

**Default**: ``same``

**Description**:

- ``same``: All jobs in a batch require the same node count
- ``any``: Jobs with different node counts may be grouped together

**Examples**:

.. code-block:: console

   --batch-spec=nodes=same
   --batch-spec=nodes=any

**Constraints**:

- ``layout=atomic`` requires ``nodes=any``
- ``layout=atomic,nodes=same`` is invalid

Count Target
~~~~~~~~~~~~

**Option**: ``count``

**Values**: ``N``, ``max``, or ``auto``

**Default**: Not specified (uses duration targeting)

**Description**:

- ``N``: Create at most N batches
- ``max``: Create maximum number of batches (one job per batch for flat, one component per batch for atomic)
- ``auto``: No longer supported (use duration targeting instead)

**Examples**:

.. code-block:: console

   --batch-spec=count=4
   --batch-spec=count=max

**Behavior**:

- ``count=N``: Subject to DAG and resource partitioning constraints
- ``count=max``: One job per batch (flat) or one component per batch (atomic)

Duration Target
~~~~~~~~~~~~~~~

**Option**: ``duration``

**Values**: Time duration (e.g., ``30m``, ``2h``, ``1h30m``)

**Default**: ``30m`` (30 minutes)

**Description**:

- Target approximate simulated runtime per batch
- Uses cheap makespan estimates for packing
- Exact final estimates optional

**Examples**:

.. code-block:: console

   --batch-spec=duration=30m
   --batch-spec=duration=2h
   --batch-spec=duration=1h30m

Workers
~~~~~~~

**Option**: ``workers``

**Values**: Positive integer

**Default**: Not specified (uses backend default)

**Description**:

- Number of workers for batch execution
- Controls parallelism within batches

**Examples**:

.. code-block:: console

   --batch-spec=workers=4
   --batch-spec=workers=8

Default Batch Specification
---------------------------

**Default**: ``layout=flat,nodes=same,duration=30m``

**Description**:

- Flat layout (no intra-batch dependencies)
- Same node count policy
- 30-minute duration target
- No explicit count or worker limits

**Example**:

.. code-block:: console

   # Uses default batch specification
   python3 -m canary hpc run --backend=slurm ./basic

Batch Specification Examples
----------------------------

Basic Examples
~~~~~~~~~~~~~~

.. code-block:: console

   # Default specification
   python3 -m canary hpc run --backend=slurm ./basic

   # Explicit default
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,nodes=same,duration=30m ./basic

Flat Layout Examples
~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Flat layout with 30-minute duration
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,duration=30m ./basic

   # Flat layout with same node count
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,nodes=same ./basic

   # Flat layout with 4 batches
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,count=4 ./basic

Atomic Layout Examples
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Atomic layout with any node count (required)
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any ./basic

   # Atomic layout with maximum batches
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any,count=max ./basic

   # Atomic layout with duration targeting (not supported - will use count=max)
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any,duration=30m ./basic

Duration Targeting Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # 30-minute duration target
   python3 -m canary hpc run --backend=slurm --batch-spec=duration=30m ./basic

   # 2-hour duration target
   python3 -m canary hpc run --backend=slurm --batch-spec=duration=2h ./basic

   # 1 hour 30 minute duration target
   python3 -m canary hpc run --backend=slurm --batch-spec=duration=1h30m ./basic

Count Targeting Examples
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Create 4 batches
   python3 -m canary hpc run --backend=slurm --batch-spec=count=4 ./basic

   # Create maximum batches (one job per batch)
   python3 -m canary hpc run --backend=slurm --batch-spec=count=max ./basic

Worker Configuration Examples
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # 4 workers per batch
   python3 -m canary hpc run --backend=slurm --batch-spec=workers=4 ./basic

   # 8 workers with duration targeting
   python3 -m canary hpc run --backend=slurm --batch-spec=duration=30m,workers=8 ./basic

Batch Specification Validation
------------------------------

**Valid Combinations**:

- ``layout=flat,nodes=same`` ✅
- ``layout=flat,nodes=any`` ✅
- ``layout=atomic,nodes=any`` ✅
- ``layout=flat,count=N`` ✅
- ``layout=flat,duration=T`` ✅
- ``layout=atomic,count=max`` ✅

**Invalid Combinations**:

- ``layout=atomic,nodes=same`` ❌ (atomic requires nodes=any)
- ``count=auto`` ❌ (no longer supported)
- ``layout=atomic,duration=T`` ❌ (duration-targeted atomic batching unsupported)

Batch Specification Behavior
----------------------------

Batching Process
~~~~~~~~~~~~~~~~

The batching process involves:

1. **Job Collection**: Gather jobs from specified paths
2. **Job Partitioning**: Group jobs by topological level and node count
3. **Batch Formation**: Apply batch specification to create batches
4. **Dependency Configuration**: Set batch dependencies globally
5. **Resource Validation**: Validate resource requirements

Partitioning Logic
~~~~~~~~~~~~~~~~~~

**Flat Layout**:

- Jobs partitioned by topological level
- Further partitioned by node count (if ``nodes=same``)
- Jobs grouped to approximate duration target

**Atomic Layout**:

- Dependency-connected components kept together
- Components partitioned by topological level
- No duration targeting (uses ``count=max``)

Resource Capacity
~~~~~~~~~~~~~~~~~

Resource capacity derived from:

- Backend resources per node
- ``node_count`` from backend
- ``count_per_node(resource_type)`` from backend
- Scheduler simulation width computed by HPC integration layer

Batch Dependencies
~~~~~~~~~~~~~~~~~~

- Set globally after partitioning
- Respect job dependencies within batches
- Configure inter-batch dependencies
- Ensure proper execution order

Batch Specification Internals
-----------------------------

Batching Implementation
~~~~~~~~~~~~~~~~~~~~~~~

The batching implementation uses:

- ``ScheduleTask`` objects for job representation
- Task width based on CPU requirements
- Duration based on estimated runtime
- Node/resource demands from ``job.required_resources()``
- Cheap makespan estimates for initial packing
- Optional exact final estimates for refinement

Batching Functions
~~~~~~~~~~~~~~~~~~

Key batching functions from ``batching.py``:

- ``partition_jobs()``: Partition jobs by layout and node policy
- ``allocate_partition_counts()``: Allocate jobs to partitions
- ``batch_jobs()``: Create batches from partitions
- ``normalize_batching_spec()``: Normalize batch specification
- ``set_batch_dependencies()``: Configure batch dependencies

Batch Specification Debugging
-----------------------------

Debugging batch specification issues:

.. code-block:: console

   # Show batch specification help
   python3 -m canary hpc help --spec

   # Test with verbose logging
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,duration=30m --verbose ./basic

   # Check batch formation
   python3 -m canary hpc run --backend=slurm --batch-spec=count=4 --verbose ./basic

Batch Specification Limitations
-------------------------------

1. **Layout Constraints**: Atomic layout requires ``nodes=any``
2. **Count Limitations**: ``count=auto`` no longer supported
3. **Duration Constraints**: Duration-targeted atomic batching unsupported
4. **Resource Constraints**: Limited by backend resource availability
5. **Dependency Constraints**: Complex dependencies may limit batching efficiency
6. **Scheduler Constraints**: Backend capabilities affect batching behavior

Batch Specification Best Practices
----------------------------------

1. **Start Simple**: Use default specification for initial testing
2. **Layout Selection**: Choose layout based on job dependencies
3. **Node Policy**: Use ``nodes=same`` for consistent workloads
4. **Duration Targeting**: Use duration for workload-based batching
5. **Count Targeting**: Use count for specific batch requirements
6. **Worker Configuration**: Match workers to backend capabilities
7. **Validation**: Test batch specifications with verbose logging
8. **Documentation**: Record working batch specifications