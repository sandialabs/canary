.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

HPC Backends
=============

The ``canary_hpc`` extension supports multiple HPC scheduler backends through `hpc_connect`. Each backend provides scheduler-specific functionality while following Canary's common HPC integration pattern.

hpc_connect Integration
-----------------------

The ``canary_hpc`` extension uses `hpc_connect` as an external dependency for backend management:

**External Dependency**:

- ``hpc_connect`` is a separate package, not part of Canary core
- ``canary_hpc`` uses ``hpc_connect.get_backend(...)`` to obtain backend instances
- Backend-specific behavior is provided by ``hpc_connect`` implementations
- Canary does not generate or vendor ``hpc_connect`` API documentation

**Backend Information**:

The extension uses ``hpc_connect`` backend methods to discover resource information:

- ``node_count``: Number of nodes available in the backend
- ``resource_types()``: Resource types supported by the backend
- ``count_per_node(resource_type)``: Count of specific resource per node
- ``supports_dependencies()``: Whether the backend supports job dependencies

**Backend Selection**:

Backends can be selected via:

- Command line: ``--backend=BACKEND``
- Environment variable: ``CANARY_HPC_BACKEND``
- Configuration files: HPC-specific configuration

Supported Backends
------------------

Slurm Backend
~~~~~~~~~~~~~

**Backend Name**: ``slurm``

**Description**: Integration with SLURM workload manager

**Features**:

- Job submission via ``sbatch``
- Resource allocation through SLURM partitions
- Queue management and prioritization
- Job dependency support
- Time limits and constraints

**Configuration**:

.. code-block:: console

   # Use Slurm backend
   python3 -m canary hpc run --backend=slurm ./basic

   # With Slurm-specific arguments
   python3 -m canary hpc run --backend=slurm --submit-arg="-A myacct,-q debug" ./basic

**Resource Information**:

- Node count from SLURM configuration
- CPU, memory, and GPU resources
- Partition-specific resource limits
- Queue time limits and constraints

PBS Backend
~~~~~~~~~~~

**Backend Name**: ``pbs``

**Description**: Integration with Portable Batch System

**Features**:

- Job submission via ``qsub``
- Resource allocation through PBS queues
- Job dependency management
- Resource reservation and limits
- Queue prioritization

**Configuration**:

.. code-block:: console

   # Use PBS backend
   python3 -m canary hpc run --backend=pbs ./basic

   # With PBS-specific arguments
   python3 -m canary hpc run --backend=pbs --submit-arg="-q workq,-l walltime=2:00:00" ./basic

**Resource Information**:

- Node count from PBS configuration
- CPU, memory, and specialized resources
- Queue-specific resource limits
- Walltime constraints

Flux Backend
~~~~~~~~~~~~

**Backend Name**: ``flux``

**Description**: Integration with Flux Framework

**Features**:

- Lightweight job submission
- Dynamic resource allocation
- Job dependency graph support
- Resource monitoring and management
- Scalable job execution

**Configuration**:

.. code-block:: console

   # Use Flux backend
   python3 -m canary hpc run --backend=flux ./basic

   # With Flux-specific arguments
   python3 -m canary hpc run --backend=flux --submit-arg="--flags=debug" ./basic

**Resource Information**:

- Node count from Flux instance
- CPU and memory resources
- Dynamic resource allocation
- Job graph dependencies

Shell Backend
~~~~~~~~~~~~~

**Backend Name**: ``shell``

**Description**: Local shell execution for testing and development

**Features**:

- Local execution without scheduler
- Deterministic testing environment
- No queue waiting or scheduling
- Immediate job execution
- Debugging and development support

**Configuration**:

.. code-block:: console

   # Use shell backend for testing
   python3 -m canary hpc run --backend=shell ./basic

   # With shell backend and batch specification
   python3 -m canary hpc run --backend=shell --batch-spec=count=4 ./basic

**Resource Information**:

- Local machine resources
- No scheduler constraints
- Immediate resource availability
- Deterministic execution environment

Backend Resource Pool
---------------------

In HPC mode, the resource pool is constructed from ``hpc_connect`` backend information:

**Resource Pool Construction**:

The ``fill_hpc_resource_pool()`` function:

1. Obtains backend from ``hpc_connect.get_backend(...)``
2. Queries backend resource information
3. Constructs topology-aware resource pool
4. Sets ``allow_multinode: true``
5. Creates virtual/backend-local node IDs
6. Adds backend resource types

**Resource Pool Characteristics**:

- **Topology-Aware**: Understands node relationships and resource distribution
- **Virtual Node IDs**: Uses backend-local node identifiers
- **Resource Types**: Includes backend-specific resource types plus ``cpus`` and ``gpus``
- **Multi-Node Support**: ``allow_multinode: true`` enables multi-node job execution
- **GPU Vendor Property**: GPU resources get vendor property ``UNKNOWN``

**Resource Pool Example**:

.. code-block:: json

   {
     "allow_multinode": true,
     "nodes": [
       {
         "id": "node-0",
         "resources": {
           "cpus": [{"id": "0", "slots": 4}, {"id": "1", "slots": 4}],
           "gpus": [{"id": "0", "slots": 1, "properties": {"vendor": "UNKNOWN"}}]
         }
       },
       {
         "id": "node-1",
         "resources": {
           "cpus": [{"id": "0", "slots": 4}, {"id": "1", "slots": 4}]
         }
       }
     ]
   }

Resource Pool Constraints
-------------------------

**Resource Pool Override Rejection**:

In HPC mode, Canary resource pool overrides are rejected:

- ``-r`` / resource pool modifiers: **Rejected**
- ``--resource-pool-file``: **Rejected**
- ``--oversubscribe``: **Rejected**

**Rationale**: HPC resources are defined by the scheduler backend, not by Canary configuration.

**User Guidance**:

- Configure resources through the selected ``hpc_connect`` backend
- Use backend-specific configuration for resource management
- Do not attempt to override HPC resource pools through Canary options

Backend Selection Behavior
---------------------------

**Backend Detection**:

The extension detects available backends through ``hpc_connect``:

.. code-block:: python

   # Get available backends
   import hpc_connect
   backends = hpc_connect.list_backends()

**Backend Validation**:

Selected backends are validated before use:

.. code-block:: python

   # Validate backend
   backend = hpc_connect.get_backend("slurm")
   if backend is None:
       raise ValueError("Backend not available")

**Backend Information Display**:

The ``hpc info`` command shows backend information:

.. code-block:: console

   # Show Slurm backend info
   python3 -m canary hpc info slurm

   # Show all available backends
   python3 -m canary hpc info pbs
   python3 -m canary hpc info flux
   python3 -m canary hpc info shell

Backend Configuration Examples
------------------------------

**Slurm Configuration**:

.. code-block:: console

   # Slurm with account and queue
   python3 -m canary hpc run --backend=slurm --submit-arg="-A myacct,-q debug" ./basic

   # Slurm with time limit
   python3 -m canary hpc run --backend=slurm --submit-arg="-t 2:00:00" ./basic

**PBS Configuration**:

.. code-block:: console

   # PBS with queue and walltime
   python3 -m canary hpc run --backend=pbs --submit-arg="-q workq,-l walltime=2:00:00" ./basic

   # PBS with resource limits
   python3 -m canary hpc run --backend=pbs --submit-arg="-l nodes=4:ppn=8" ./basic

**Shell Configuration**:

.. code-block:: console

   # Shell backend for testing
   python3 -m canary hpc run --backend=shell --batch-spec=count=4 ./basic

   # Shell with workers
   python3 -m canary hpc run --backend=shell --workers=2 ./basic

Backend Debugging
-----------------

**Backend Detection Issues**:

.. code-block:: console

   # Check available backends
   python3 -m canary hpc info slurm

   # Test with verbose logging
   python3 -m canary hpc run --backend=slurm --verbose ./basic

**Resource Pool Issues**:

.. code-block:: console

   # Check HPC resource pool
   python3 -m canary config show resource-pool --backend=slurm

   # Test resource allocation
   python3 -m canary hpc run --backend=slurm -p "nodes=2,cpus=8" ./basic

**Backend Configuration Issues**:

.. code-block:: console

   # Check backend configuration
   python3 -c "import hpc_connect; print(hpc_connect.get_backend('slurm'))"

   # Test backend manually
   python3 -m canary hpc info slurm

Backend Limitations
-------------------

1. **Backend Dependency**: Requires ``hpc_connect`` backend configuration
2. **Resource Constraints**: Limited by backend resource availability
3. **Scheduler-Specific**: Behavior depends on backend capabilities
4. **Configuration Complexity**: Backend configuration can be complex
5. **Debugging Challenges**: Backend-specific issues may be difficult to diagnose
6. **No API Documentation**: Canary does not document ``hpc_connect`` API details

Backend Best Practices
----------------------

1. **Backend Selection**: Choose appropriate backend for your HPC environment
2. **Configuration**: Configure backend resources properly
3. **Testing**: Test with shell backend before using production schedulers
4. **Debugging**: Use verbose logging for backend issues
5. **Documentation**: Document backend configurations and requirements
6. **Validation**: Validate backend availability before execution
7. **Resource Management**: Configure resources in backend, not through Canary overrides