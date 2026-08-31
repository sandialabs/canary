.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Resource Management
===================

The ``canary_flux`` extension implements a comprehensive resource management model that integrates Canary's resource requirements with Flux's resource allocation capabilities. This model ensures efficient resource utilization and accurate job placement.

Resource Pool Creation
======================

The Flux extension creates resource pools from the `hpc_connect` Flux backend during the ``canary_resource_pool_fill`` hook. This process queries the backend for available resources and constructs a topology-aware resource pool.

Backend Resource Discovery
--------------------------

The extension queries the Flux backend for resource information:

**Node Count**:
- Primary source: ``backend.node_count`` property
- Can be overridden with ``--nodes`` command-line argument
- Determines number of virtual nodes in resource pool

**Resource Types**:
- Primary source: ``backend.resource_types()`` method
- Default types: ``cpus``, ``gpus``
- Additional types reported by backend are included

**Resource Counts**:
- Primary source: ``backend.count_per_node(rtype)`` method
- Handles both singular and plural resource type names
- Returns count per node for each resource type

**Fallback Values**:
- CPUs: Defaults to 1 if backend doesn't report or reports ≤ 0
- GPUs: Defaults to 0 if backend doesn't report
- Other resources: Only included if backend reports positive count

Resource Type Normalization
---------------------------

The extension normalizes resource type names for consistent handling:

**Canonical Form**:
- Resource types should end with "s" (plural)
- ``_canonical_resource_type(rtype)`` adds "s" if not present

**Singular Form**:
- ``_singular_resource_type(rtype)`` removes "s" if present
- Used for backend queries that expect singular names

**Query Strategy**:
- Tries multiple name variants when querying backend
- Falls back through singular → plural → original names
- Uses first variant that returns positive count

Resource Pool Structure
-----------------------

The generated resource pool has the following structure:

**Top-Level Properties**:
- ``allow_multinode``: ``true`` (enables multi-node jobs)
- ``additional_properties``: Metadata about pool source and backend

**Node Properties**:
- ``id``: String node ID (``"0"``, ``"1"``, ``"2"``, ...)
- ``resources``: Dictionary mapping resource types to resource lists

**Resource Properties**:
- ``id``: String resource ID (``"0"``, ``"1"``, ...)
- ``slots``: Number of slots (typically 1)
- ``properties``: Optional resource-specific properties (e.g., GPU vendor)

**Example Pool Structure**:

.. code-block:: json

   {
     "allow_multinode": true,
     "additional_properties": {
       "source": "canary_flux",
       "backend": "flux",
       "node_count": 4,
       "cpus_per_node": 32,
       "gpus_per_node": 4
     },
     "nodes": [
       {
         "id": "0",
         "resources": {
           "cpus": [
             {"id": "0", "slots": 1},
             {"id": "1", "slots": 1},
             "..."
           ],
           "gpus": [
             {"id": "0", "slots": 1, "properties": {"vendor": "UNKNOWN"}},
             {"id": "1", "slots": 1, "properties": {"vendor": "UNKNOWN"}},
             "..."
           ]
         }
       },
       {
         "id": "1",
         "resources": {
           "cpus": "...",
           "gpus": "..."
         }
       }
     ]
   }

Resource Assignment
===================

The Flux extension assigns resources to jobs through the ``assign_flux_resources`` function, which runs during ``canary flux exec`` execution. This function creates resource assignments based on the Flux environment.

GPU Resource Assignment
-----------------------

GPU resources are assigned from Flux environment variables:

**Environment Variables**:
- ``CUDA_VISIBLE_DEVICES``: For CUDA GPUs
- ``ROCR_VISIBLE_DEVICES``: For ROCr/HIP GPUs
- ``HIP_VISIBLE_DEVICES``: For HIP GPUs
- ``GPU_DEVICE_ORDINAL``: Generic GPU ordinal

**Assignment Process**:
- Reads first available environment variable
- Splits value by commas to get GPU IDs
- Creates GPU resource entries with Flux job ID as node
- Sets ``CANARY_GPU_IDS`` variable for job use

**Example**:
- Environment: ``CUDA_VISIBLE_DEVICES="0,1,2"``
- Assignment: 3 GPUs with IDs ``"0"``, ``"1"``, ``"2"``
- Variable: ``CANARY_GPU_IDS="0,1,2"``

CPU Resource Assignment
-----------------------

CPU resources are assigned based on job requirements:

**Assignment Process**:
- Gets CPU count from job's ``cpus`` attribute (defaults to 1)
- Creates CPU resource entries with Flux job ID as node
- Assigns sequential CPU IDs starting from 0

**Example**:
- Job CPUs: 4
- Assignment: 4 CPUs with IDs ``"0"``, ``"1"``, ``"2"``, ``"3"``

Metadata Assignment
-------------------

Additional metadata is attached to resource assignments:

**Assignment Metadata**:
- ``source``: ``"canary_flux"``
- ``flux_jobid``: From ``FLUX_JOB_ID`` environment variable
- ``flux_uri``: From ``FLUX_URI`` environment variable

**Purpose**:
- Tracks resource assignment source
- Enables debugging and troubleshooting
- Provides Flux context for resource usage

Resource Requirements
=====================

Jobs specify resource requirements through Canary's standard mechanisms:

**CPU Requirements**:
- ``job.cpus``: Number of CPUs required
- Used for CPU resource assignment
- Defaults to 1 if not specified

**GPU Requirements**:
- ``job.gpus``: Number of GPUs required
- Validated against assigned GPUs
- Defaults to 0 if not specified

**Node Requirements**:
- ``job.nodes``: Number of nodes required
- Must be ≤ allocation node count
- Validated before submission

**Resource Validation**:
- ``job.required_resources()`` returns list of required resource IDs
- Validates that job requirements match available resources
- Raises error if job requires more nodes than allocation

Resource Utilization Tracking
=============================

The Flux extension tracks resource utilization through various mechanisms:

**Job Measurements**:
- ``flux`` measurement key contains comprehensive resource and timing data
- Includes resource counts, job IDs, and timing metrics
- Persisted to job workspace for analysis

**Process Info**:
- ``procinfo.json`` file in submit workspace
- Contains Flux process information and resource usage
- Written after job completion

**Environment Capture**:
- ``env.json`` file in job workspace
- Contains full environment at job finish
- Includes all Flux environment variables

Resource Pool Behavior
======================

The Flux extension modifies Canary's resource pool behavior:

**Pool Override Rejection**:
- Command-line resource pool overrides rejected (``-r``, ``--resource-pool-file``)
- ``--oversubscribe`` option rejected
- Users must configure resources in `hpc_connect` backend

**Backend-Driven Configuration**:
- Resource pool determined by Flux backend
- Node count, resource types, and counts come from backend
- Ensures consistency with actual Flux resources

**Virtual Node IDs**:
- Node IDs are virtual (``"0"``, ``"1"``, ...)
- Not tied to physical hardware IDs
- Enables consistent resource pool across different Flux instances

Resource Management Examples
============================

Basic Resource Pool
-------------------

.. code-block:: console

   # Query backend with 4 nodes, 32 CPUs, 4 GPUs per node
   python3 -m canary flux run ./basic

   # Result: Resource pool with 4 nodes
   # Node 0: 32 CPUs, 4 GPUs
   # Node 1: 32 CPUs, 4 GPUs
   # Node 2: 32 CPUs, 4 GPUs
   # Node 3: 32 CPUs, 4 GPUs

Custom Node Count
-----------------

.. code-block:: console

   # Override backend node count
   python3 -m canary flux run --nodes 2 ./basic

   # Result: Resource pool with 2 nodes
   # Node 0: 32 CPUs, 4 GPUs (from backend)
   # Node 1: 32 CPUs, 4 GPUs (from backend)

Resource Assignment in Jobs
---------------------------

.. code-block:: python

   # Job requiring 8 CPUs and 2 GPUs
   def test_example():
       assert canary.config.cpus == 8
       assert canary.config.gpus == 2
       # GPUs available in CUDA_VISIBLE_DEVICES
       # CPUs assigned from resource pool

Resource Validation
-------------------

.. code-block:: console

   # Job requiring 5 nodes (fails if allocation has only 4)
   python3 -m canary flux run ./multi-node-test
   # Error: "job requires more nodes than exist in this flux resource pool"

Debugging Resource Issues
==========================

The Flux extension provides several tools for debugging resource issues:

**Environment Inspection**:
- Check ``env.json`` in job workspace for Flux environment variables
- Verify ``CUDA_VISIBLE_DEVICES``, ``FLUX_JOB_ID``, etc.

**Resource Pool Inspection**:
- Resource pool structure logged during creation
- Check ``additional_properties`` for backend information

**Process Info Inspection**:
- Check ``procinfo.json`` in submit workspace for Flux process details
- Verify resource usage and job metadata

**Timing Analysis**:
- Check ``flux`` measurements in job for timing metrics
- Analyze allocation wait times and job overheads

Best Practices
==============

1. **Backend Configuration**: Configure `hpc_connect` backend with accurate resource counts
2. **Node Count**: Start with auto-detection, then optimize based on workload
3. **Resource Requirements**: Specify accurate CPU/GPU requirements in job specifications
4. **Validation**: Check that job requirements match backend resources
5. **Debugging**: Use environment capture and process info for troubleshooting
6. **Monitoring**: Track resource utilization through job measurements
7. **Documentation**: Record resource configurations and requirements

Resource Management Comparison
==============================

**Flux Extension (canary_flux)**:
- Direct resource pool from Flux backend
- Individual job resource assignment
- Fine-grained resource control
- Automatic GPU/CPU assignment from environment
- Lower overhead per job

**HPC Extension (canary_hpc)**:
- Resource pool from HPC backend
- Batch-level resource management
- Resource assignment through batch context
- Higher overhead due to batching
- More complex resource flow

Use Flux extension for direct, fine-grained resource management. Use HPC extension for batching and multi-backend resource handling.
