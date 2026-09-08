.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Backends
========

The ``canary_flux`` extension integrates with Flux Framework through `hpc_connect`, using backend abstractions for Flux resource management and job submission.

Backend Integration
===================

**Key Characteristics**:

- **Direct Integration**: Uses ``hpc_connect.get_backend("flux")`` for Flux access
- **Backend Selection**: Supports ``--flux-backend`` option for backend override
- **Default Backend**: Uses "flux" backend if not specified
- **Resource Discovery**: Queries backend for node count, resource types, and counts

**Backend Requirements**:

1. Must implement ``hpc_connect.Backend`` interface
2. Must support Flux allocation management
3. Must provide job submission capabilities
4. Must report resource information accurately

**Backend Properties Used**:

- ``backend.node_count``: Number of available nodes
- ``backend.name``: Backend identifier
- ``backend.resource_types()``: Available resource types
- ``backend.count_per_node(rtype)``: Count of each resource type per node
- ``backend.submission_manager()``: Job submission interface

Backend Configuration
=====================

**Backend Selection**:

.. code-block:: console

   # Use default "flux" backend
   python3 -m canary flux run ./basic

   # Use specific backend
   python3 -m canary flux run --flux-backend=myflux ./basic

**Resource Discovery**:

**Node Count**:
1. Command-line ``--nodes`` argument (highest priority)
2. ``backend.node_count`` property
3. Auto-detection based on allocation

**Resource Types**:
1. ``backend.resource_types()`` method
2. Default types: ``cpus``, ``gpus``
3. Additional types reported by backend

**Resource Counts**:
1. ``backend.count_per_node(rtype)`` method
2. Handles singular/plural resource type names
3. Fallback values: CPUs=1, GPUs=0

**Resource Type Normalization**:

- **Canonical Form**: Resource types end with "s" (plural)
- **Singular Form**: Removes "s" for backend queries
- **Query Strategy**: Tries multiple name variants, uses first positive result

Backend Resource Pool
=====================

**Pool Structure**:

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
           "cpus": [{"id": "0", "slots": 1}, "..."],
           "gpus": [{"id": "0", "slots": 1, "properties": {"vendor": "UNKNOWN"}}, "..."]
         }
       }
     ]
   }

Flux Framework Backend
======================

**Allocation Management**:
- ``FluxAllocation`` context for resource allocation
- ``allocation.open()`` with timeout support
- Allocation lifecycle management

**Job Submission**:
- ``submission_manager()`` for job submission
- ``JobSpec`` creation with resource requirements
- Flux job lifecycle callbacks

**Resource Reporting**:
- Node count and resource types
- Per-node resource counts
- GPU/CPU resource information

Backend Limitations
===================

**Constraints**:
- Command-line resource pool overrides rejected
- Users must configure resources in backend
- Resource pool determined by backend capabilities
- Requires properly configured `hpc_connect` Flux backend

**Error Handling**:
- Backend errors propagated to Flux extension
- Resource discovery failures use fallback values
- Missing backend methods handled gracefully

Backend Comparison
==================

**Flux Extension (canary_flux)**:
- Direct Flux backend integration
- Individual job submission
- Fine-grained resource control
- Backend-driven resource pool

**HPC Extension (canary_hpc)**:
- Multiple backend support
- Batching layer
- Batch-level resource management
- More complex backend interaction

Backend Best Practices
======================

1. Configure `hpc_connect` backend with accurate resource counts
2. Start with auto-detection, then optimize based on workload
3. Ensure backend reports correct resource types and counts
4. Configure backend to handle errors appropriately
5. Use backend logs and resource pool inspection for troubleshooting

Backend Troubleshooting
=======================

**Backend Not Found**:
- Check backend name and configuration
- Verify backend is properly configured in `hpc_connect`

**Resource Discovery Failure**:
- Check backend ``resource_types()`` and ``count_per_node()`` methods
- Configure backend to report accurate resource information

**Allocation Failure**:
- Check backend allocation configuration
- Verify backend supports requested node count and resources

**Submission Failure**:
- Check backend submission manager
- Verify backend submission capabilities and limits
