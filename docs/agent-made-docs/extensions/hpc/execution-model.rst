.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Execution Model
===============

The ``canary_hpc`` extension implements a batch-oriented execution model that replaces Canary's local test execution with HPC scheduler submission. This model enables efficient execution of test suites on high-performance computing systems.

Local vs HPC Execution
----------------------

**Local Execution** (``canary run``):

- Jobs execute immediately on local machine
- No batching or scheduling
- Direct resource access
- Simple execution flow

**HPC Execution** (``canary hpc run``):

- Jobs grouped into batches
- Batches submitted to HPC scheduler
- Resource allocation through scheduler
- Nested Canary execution in batch workspace
- Complex execution flow with multiple phases

Execution Phases
----------------

The HPC execution model consists of several phases:

1. **Job Collection and Selection**
   - Canary collects test jobs from specified paths
   - Jobs filtered by selection criteria
   - Resource requirements validated

2. **Batch Formation**
   - Jobs grouped into batches based on batch specification
   - Batch metadata and configuration prepared
   - Batch workspaces created

3. **Resource Allocation**
   - HPC backend resources discovered
   - Topology-aware resource pool constructed
   - Resources allocated to batches

4. **Batch Submission**
   - Batches submitted to HPC scheduler via `hpc_connect`
   - Scheduler job scripts generated
   - Batch dependencies configured

5. **Nested Execution**
   - Canary executed inside batch workspace
   - Batch-local resource pool used
   - Jobs run with allocated resources

6. **Result Collection**
   - Results gathered from batch execution
   - Status aggregated from child jobs
   - Output files collected

7. **Status Aggregation**
   - Batch status determined
   - Child job status updated
   - Final results reported

Batch Formation Process
-----------------------

The batch formation process involves:

1. **Job Partitioning**:
   - Jobs grouped by topological level
   - Partitioned by node count requirements
   - Organized by resource needs

2. **Batch Specification Application**:
   - Layout policy applied (flat or atomic)
   - Node policy applied (same or any)
   - Count or duration targets applied

3. **Batch Creation**:
   - ``TestBatch`` objects created
   - Batch metadata recorded
   - Batch workspaces prepared

4. **Dependency Configuration**:
   - Batch dependencies set
   - Execution order determined
   - Resource constraints validated

Nested Execution Model
----------------------

The nested execution model enables Canary to run within batch workspaces:

**Outer Execution** (Submission Host):

- ``canary hpc run`` command
- Batch formation and submission
- Resource pool management
- Status monitoring

**Inner Execution** (Batch Workspace):

- ``canary hpc exec`` command
- Batch-local resource pool
- Job execution with allocated resources
- Result generation

**Communication**:

- Batch workspace contains metadata and configuration
- ``resource_pool.json`` defines batch-local resources
- ``batch.lock`` records batch state
- Results copied back to submission host

Resource Management
-------------------

HPC resource management differs from local execution:

**Local Resources**:

- Direct access to local machine resources
- Simple resource allocation
- No resource pool construction needed

**HPC Resources**:

- Backend-driven resource discovery
- Topology-aware resource pool construction
- Virtual/backend-local node IDs
- Batch-specific resource allocation
- Resource preflight validation

Resource Pool Construction
~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``fill_hpc_resource_pool()`` function:

1. Obtains backend from `hpc_connect`
2. Queries backend resource information
3. Constructs topology-aware resource pool
4. Sets ``allow_multinode: true``
5. Creates virtual node IDs
6. Adds backend resource types

Batch Resource Pool
~~~~~~~~~~~~~~~~~~~

The ``fill_batch_resource_pool()`` function:

1. Loads ``resource_pool.json`` from batch workspace
2. Creates batch-local resource pool
3. Validates resource requirements
4. Provides resources to nested execution

Execution Flow Comparison
-------------------------

**Local Execution Flow**:

1. Collect jobs
2. Filter jobs
3. Execute jobs locally
4. Report results

**HPC Execution Flow**:

1. Collect jobs
2. Filter jobs
3. Form batches
4. Submit batches to scheduler
5. Execute batches via nested Canary
6. Collect results from batches
7. Aggregate status
8. Report final results

Batch Workspace Structure
--------------------------

Each batch workspace contains:

.. code-block:: text

   .canary/cache/canary-hpc/batches/<batch-id-prefix>/
   ├── batch.lock              # Batch metadata and state
   ├── resource_pool.json      # Batch-local resource pool
   ├── config.json             # Configuration snapshot
   ├── canary-inp.sh           # Input script (if generated)
   ├── logs/                   # Execution logs
   └── results/                # Job results

Batch Metadata
~~~~~~~~~~~~~~

The ``batch.lock`` file contains:

- Batch ID and configuration
- Job list and dependencies
- Resource allocation
- Status information
- Timestamps and execution data

Resource Pool File
~~~~~~~~~~~~~~~~~~

The ``resource_pool.json`` file contains:

- Batch-local topology-aware resource pool
- Node definitions and resources
- Resource properties and constraints
- Allocation metadata

Configuration Snapshot
~~~~~~~~~~~~~~~~~~~~~~

The ``config.json`` file contains:

- Canary configuration snapshot
- Batch-specific settings
- Environment information
- Execution parameters

Execution Model Benefits
------------------------

The HPC execution model provides several benefits:

1. **Resource Efficiency**: Batches optimize scheduler resource utilization
2. **Scalability**: Enables execution on large HPC systems
3. **Isolation**: Batch workspaces provide execution isolation
4. **Flexibility**: Supports multiple scheduler backends
5. **Monitoring**: Batch status tracking and aggregation
6. **Debugging**: Comprehensive logging and metadata

Execution Model Limitations
---------------------------

The HPC execution model also has limitations:

1. **Complexity**: More complex than local execution
2. **Overhead**: Batch formation and submission add overhead
3. **Dependencies**: Requires `hpc_connect` backend configuration
4. **Resource Constraints**: Limited by scheduler resource availability
5. **Timeout Risks**: Queue and run timeouts can cancel execution
6. **Debugging Complexity**: Nested execution adds debugging complexity

These limitations should be considered when choosing between local and HPC execution.