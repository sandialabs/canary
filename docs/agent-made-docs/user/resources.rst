.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-resources:

Resources
=========

Canary's resource management system tracks and allocates hardware resources for test execution. This system ensures that tests have access to the resources they require while preventing overallocation and resource conflicts.

Resource Pool Architecture
--------------------------

The resource pool is a topology-aware inventory of available hardware resources organized into nodes. Each node represents a compute resource (typically a physical machine) with its own set of resources.

.. code-block:: yaml

   resource_pool:
     allow_multinode: true
     additional_properties: {}
     nodes:
     - id: node-0
       resources:
         cpus:
         - id: "0"
           slots: 1
         - id: "1"
           slots: 1
         gpus:
         - id: "0"
           slots: 1

Key Components:

- **Node**: A single compute resource with its own inventory of resources
- **Resource Type**: A category of hardware resource (e.g., "cpus", "gpus")
- **Resource Instance**: A specific hardware unit with an ID and available slots
- **Slots**: The number of concurrent allocations available for a resource instance

Resource Types
--------------

Canary supports any resource type, with built-in detection for:

- **cpus**: CPU cores (automatically detected)
- **gpus**: GPU devices (NVIDIA GPUs automatically detected)

Additional resource types (e.g., "fpgas", "accelerators") can be defined by users.

Resource Specification
----------------------

Resources are specified as dictionaries with:

- **id**: Unique identifier for the resource instance
- **slots**: Number of concurrent allocations (default: 1)

Example resource specifications:

.. code-block:: yaml

   # Single CPU core
   - id: "0"
     slots: 1

   # GPU with 4 slots
   - id: "0"
     slots: 4

Resource Allocation
-------------------

Tests request resources through parameters that match resource pool types:

.. code-block:: python

   canary_pyt.directives.parameterize("cpus,gpus", [(4, 2)])

The resource manager:

1. **Accommodates**: Checks if sufficient resources are available
2. **Scores**: Selects the optimal node based on residual capacity
3. **Checkouts**: Allocates resources to the test
4. **Checkins**: Returns resources when the test completes

Multi-Node Allocation
---------------------

For distributed execution, tests can request resources across multiple nodes:

.. code-block:: python

   # Request 2 nodes, each with 4 CPUs and 1 GPU
   resources = [
       {"type": "nodes", "slots": 2},
       {"type": "cpus", "slots": 4},
       {"type": "gpus", "slots": 1}
   ]

The resource pool must have ``allow_multinode: true`` for multi-node allocation.

Resource Discovery
------------------

Canary discovers resources through:

1. **Automatic Detection**: CPUs via system probe, GPUs via NVIDIA detection
2. **Command Line**: ``-r cpus=8,gpus=4``
3. **Configuration File**: ``--resource-pool-file=FILE.yaml``
4. **Plugins**: Extension-specific resource discovery hooks

Viewing Resources
-----------------

Inspect the current resource pool:

.. code-block:: console

   $ canary config show resource-pool
   resource_pool:
     allow_multinode: true
     nodes:
     - id: hostname
       resources:
         cpus:
         - id: "0"
           slots: 1
         # ... additional CPUs
         gpus:
         - id: "0"
           slots: 1

Environment Variables
---------------------

Allocated resources are exposed to tests via environment variables:

- ``CANARY_<RESOURCE>_IDS``: Comma-separated list of allocated resource IDs
- ``%(resource_ids)s``: Template substitution in existing environment variables

Example:

.. code-block:: python

   # If CUDA_VISIBLE_DEVICES="%(gpu_ids)s" and GPUs 0,1,2 are allocated
   # Result: CUDA_VISIBLE_DEVICES="0,1,2"

Resource Management Lifecycle
-----------------------------

1. **Initialization**: Resource pool created from discovery
2. **Allocation**: Resources checked out for test execution
3. **Execution**: Test runs with allocated resources
4. **Release**: Resources checked back into the pool
5. **Cleanup**: Resource pool released when workspace closes

Best Practices
--------------

- **Explicit Declaration**: Always declare resource requirements in test parameters
- **Realistic Slots**: Set slots based on actual hardware capabilities
- **Resource Types**: Define all resource types used by tests, even with zero count
- **Multi-Node**: Use multi-node allocation only when necessary for distributed tests

Troubleshooting
---------------

**Insufficient Resources**:

.. code-block:: console

   $ canary run my_test.pyt
   Error: insufficient slots on node hostname of cpus (requested 16, available 8)

Solution: Reduce test requirements or increase resource pool capacity.

**Unknown Resource Type**:

.. code-block:: console

   $ canary run my_test.pyt
   Error: Resource 'fpgas' unavailable on node hostname

Solution: Add the resource type to the resource pool configuration.

See Also
--------

- :doc:`concepts`: Core architectural concepts
- :doc:`jobs`: Job structure and lifecycle
- :doc:`running`: Execution configuration and resource allocation
- :doc:`/reference/commands.run`: Run command reference
