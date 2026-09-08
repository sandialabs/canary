.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Resources
=========

The ``canary_hpc`` extension manages resources differently from local execution, using ``hpc_connect`` backend information to construct topology-aware resource pools and enforce HPC-specific constraints.

HPC Resource Management
------------------------

**Key Differences from Local Execution**:

1. **Backend-Driven**: Resources defined by ``hpc_connect`` backend
2. **Topology-Aware**: Understands node relationships and distribution
3. **Multi-Node**: Supports multi-node job execution
4. **Constraint Enforcement**: Rejects local resource pool overrides
5. **Dynamic Construction**: Resource pools built from backend information

Resource Pool Construction
--------------------------

**fill_hpc_resource_pool()**:

The ``fill_hpc_resource_pool()`` function constructs the HPC resource pool:

1. Obtains backend from ``hpc_connect.get_backend(...)``
2. Queries backend resource information
3. Constructs topology-aware resource pool
4. Sets ``allow_multinode: true``
5. Creates virtual/backend-local node IDs
6. Adds backend resource types

**Resource Pool Structure**:

.. code-block:: json

   {
     "allow_multinode": true,
     "additional_properties": {
       "source": "hpc_connect",
       "backend": "slurm"
     },
     "nodes": [
       {
         "id": "node-0",
         "resources": {
           "cpus": [
             {"id": "0", "slots": 4, "node": "node-0"},
             {"id": "1", "slots": 4, "node": "node-0"}
           ],
           "gpus": [
             {"id": "0", "slots": 1, "node": "node-0", "properties": {"vendor": "UNKNOWN"}}
           ]
         }
       },
       {
         "id": "node-1",
         "resources": {
           "cpus": [
             {"id": "0", "slots": 4, "node": "node-1"},
             {"id": "1", "slots": 4, "node": "node-1"}
           ]
         }
       }
     ]
   }

Resource Pool Characteristics
-----------------------------

**Topology-Aware**:

- Understands node relationships
- Tracks resource distribution across nodes
- Enables multi-node job execution
- Preserves backend topology

**Virtual Node IDs**:

- Backend-local node identifiers
- Not necessarily physical node names
- Used for resource allocation
- Maintains backend abstraction

**Resource Types**:

- Standard: ``cpus``, ``gpus``
- Backend-specific: Custom resource types
- Dynamic: Based on backend capabilities

**Multi-Node Support**:

- ``allow_multinode: true`` enables multi-node jobs
- Jobs can span multiple nodes
- Resource allocation respects node boundaries
- Dependency management across nodes

**GPU Vendor Property**:

- GPU resources get vendor property ``UNKNOWN``
- Enables vendor-agnostic GPU handling
- Preserves backend abstraction
- Allows vendor extensions to claim devices

Resource Pool Constraints
-------------------------

**Resource Pool Override Rejection**:

In HPC mode, Canary resource pool overrides are rejected:

**Rejected Options**:

- ``-r`` / resource pool modifiers
- ``--resource-pool-file``
- ``--oversubscribe``

**Rationale**:

- HPC resources defined by scheduler backend
- Local overrides would conflict with backend configuration
- Maintains consistent resource management

**User Guidance**:

- Configure resources through ``hpc_connect`` backend
- Use backend-specific configuration
- Do not attempt local resource pool overrides

Resource Allocation
-------------------

**Job Resource Requirements**:

Jobs specify resource requirements through Canary's standard mechanisms:

.. code-block:: python

   # Job resource specification
   {
     "cpus": 8,
     "nodes": 2,
     "gpus": 1,
     "memory": "16GB"
   }

**Resource Matching**:

- Jobs matched to available resources
- Resource requirements validated
- Allocation respects backend constraints
- Preflight validation before submission

**Resource Capacity**:

- Derived from backend resources
- ``node_count`` from backend
- ``count_per_node(resource_type)`` from backend
- Scheduler simulation width computed

Batch Resource Pool
-------------------

**Batch-Local Resource Pool**:

During nested execution, ``fill_batch_resource_pool()`` loads batch-local resource pool:

1. Loads ``resource_pool.json`` from batch workspace
2. Creates batch-local resource pool
3. Validates resource requirements
4. Provides resources to nested execution

**Batch Resource Pool File**:

.. code-block:: json

   {
     "allow_multinode": false,
     "additional_properties": {
       "source": "batch-local",
       "batch_id": "abc123"
     },
     "nodes": [
       {
         "id": "batch-node",
         "resources": {
           "cpus": [
             {"id": "0", "slots": 4, "node": "batch-node"},
             {"id": "1", "slots": 4, "node": "batch-node"}
           ]
         }
       }
     ]
   }

Resource Preflight Validation
-----------------------------

**Preflight Checks**:

- Validate job resource requirements
- Check resource availability
- Verify backend constraints
- Prevent invalid submissions

**Failure Handling**:

- Jobs marked ``BROKEN`` on preflight failure
- Specific failure reasons provided
- Prevents wasted scheduler submissions
- Enables early error detection

Resource Management Examples
----------------------------

**Slurm Resource Configuration**:

.. code-block:: console

   # Check Slurm resource pool
   python3 -m canary config show resource-pool --backend=slurm

   # Run with Slurm resources
   python3 -m canary hpc run --backend=slurm -p "nodes=2,cpus=8" ./basic

**PBS Resource Configuration**:

.. code-block:: console

   # Check PBS resource pool
   python3 -m canary config show resource-pool --backend=pbs

   # Run with PBS resources
   python3 -m canary hpc run --backend=pbs -p "nodes=4,cpus=16" ./basic

**Shell Resource Configuration**:

.. code-block:: console

   # Check shell resource pool
   python3 -m canary config show resource-pool --backend=shell

   # Run with shell resources
   python3 -m canary hpc run --backend=shell -p "cpus=4" ./basic

Resource Debugging
------------------

**Resource Pool Inspection**:

.. code-block:: console

   # Show HPC resource pool
   python3 -m canary config show resource-pool --backend=slurm

   # Check resource allocation
   python3 -m canary hpc run --backend=slurm -p "nodes=2,cpus=8" --verbose ./basic

**Resource Validation**:

.. code-block:: console

   # Test resource requirements
   python3 -m canary hpc run --backend=slurm -p "nodes=4,cpus=32,gpus=2" --verbose ./basic

   # Check preflight validation
   python3 -m canary hpc run --backend=slurm -p "nodes=100,cpus=1000" --verbose ./basic

Resource Limitations
--------------------

1. **Backend Dependency**: Resources defined by ``hpc_connect`` backend
2. **Constraint Enforcement**: Local overrides rejected
3. **Preflight Validation**: Resource checks before submission
4. **Backend Constraints**: Limited by scheduler capabilities
5. **Dynamic Resources**: Resource availability may change
6. **Multi-Node Complexity**: Multi-node allocation challenges
7. **GPU Abstraction**: Vendor-agnostic GPU handling

Resource Best Practices
-----------------------

1. **Backend Configuration**: Configure resources in ``hpc_connect`` backend
2. **Resource Validation**: Test resource requirements before submission
3. **Preflight Checking**: Use verbose logging for validation issues
4. **Constraint Awareness**: Understand backend resource limits
5. **Multi-Node Planning**: Design jobs for multi-node execution
6. **GPU Handling**: Use vendor extensions for GPU-specific needs
7. **Documentation**: Record resource configurations and requirements