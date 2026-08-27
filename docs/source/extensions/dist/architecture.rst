.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Distributed Execution Architecture
==================================

The ``canary_dist`` extension implements a distributed execution architecture that enables Canary to run tests across multiple remote machines. This architecture is designed to integrate seamlessly with Canary's existing job execution framework while providing the scalability benefits of distributed computing.

Core Components
---------------

Resource Pool Server
~~~~~~~~~~~~~~~~~~~~

The distributed resource pool server is an external service that:

- Tracks available machines and their resources (CPUs, GPUs, etc.)
- Manages machine state (online/offline)
- Handles resource checkout and checkin operations
- Provides endpoints for pool status and resource accommodation checks

Server Endpoints
~~~~~~~~~~~~~~~~

The server exposes several key endpoints used by the Canary distributed adapter:

- ``/status``: Returns current pool state including all machines and their resources
- ``/accommodates``: Checks if the pool can accommodate a specific resource request
- ``/checkout``: Reserves resources for a batch execution (returns transaction ID)
- ``/checkin``: Releases reserved resources back to the pool
- ``/rx``: Health check and cleanup of expired checkouts

Distributed Resource Pool Adapter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``DistributedResourcePoolAdapter`` translates between the server's flat resource model and Canary's topology-aware resource pool:

1. **Resource Discovery**: Queries server for available machines and resources
2. **Eligibility Filtering**: Filters machines by tags, groups, and online status
3. **Resource Translation**: Converts server resource counts to Canary's node-based model
4. **Checkout/Checkin**: Manages resource reservations with transaction tracking
5. **Capacity Calculation**: Determines maximum available capacity by resource type

Resource Translation Process
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Server returns flat resource lists per machine
2. Adapter creates one Canary node per eligible machine
3. Each node contains the machine's resources with node identity attached
4. ``allow_multinode`` is set to ``False`` (distributed execution doesn't support multi-node jobs)

Distributed Pool Conductor
~~~~~~~~~~~~~~~~~~~~~~~~~~

The conductor orchestrates the distributed execution process:

1. **Job Selection**: Filters jobs suitable for distributed execution (single-node only)
2. **Batch Creation**: Groups jobs into batches based on resource requirements
3. **Resource Allocation**: Checks out resources from the pool server
4. **Remote Submission**: Submits batches to remote machines via hpc_connect
5. **Execution Monitoring**: Tracks batch execution progress

Batch Execution Flow
--------------------

1. **Job Collection**: Canary collects and filters test jobs
2. **Batch Formation**: Jobs are grouped into batches based on:
   - Resource requirements
   - Batch width (CPU count)
   - Batch count or duration limits
3. **Resource Checkout**: Conductor checks out resources from pool server
4. **Batch Workspace Creation**: Local workspace prepared for each batch
5. **Remote Submission**: Batch submitted to remote machine via ``canary dist exec``
6. **Remote Execution**: Tests run on remote machine with local resource pool
7. **Result Collection**: Results returned to original workspace
8. **Resource Checkin**: Resources released back to pool

Nested Execution Model
----------------------

Distributed execution uses a nested Canary execution model:

1. **Outer Execution**: ``canary dist run`` runs on submission host
2. **Batch Preparation**: Creates batch workspaces with resource pool metadata
3. **Remote Invocation**: Calls ``canary dist exec`` on remote machine
4. **Inner Execution**: Remote Canary instance runs tests using batch-local resource pool
5. **Result Return**: Results copied back to submission host workspace

Resource Management
-------------------

Transaction-Based Checkout
~~~~~~~~~~~~~~~~~~~~~~~~~~

Resource checkout uses a transaction model:

- Each checkout creates a transaction ID
- Transaction ID stored in batch metadata
- Checkin uses transaction ID to release specific resources
- Server health check (``/rx``) cleans up expired transactions

Resource Allocation Metadata
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Checkout returns allocation metadata including:

- ``source``: ``"canary-dist"``
- ``server_url``: Pool server location
- ``hostname``: Remote machine hostname
- ``transaction_id``: Unique transaction identifier

Single-Node Constraint
~~~~~~~~~~~~~~~~~~~~~~

Distributed execution enforces single-node constraints:

- ``allow_multinode``: ``False`` in resource pool
- Multi-node job requests are rejected during selection
- Each batch runs on exactly one remote machine
- Resource requests must fit within single machine capacity

Environment Export
------------------

The extension provides controlled environment variable propagation:

- **Default**: No environment variables exported
- **ALL mode**: Export all environment variables
- **Selective mode**: Export specific variables by name
- **Value override**: Export variables with specific values
- **Module handling**: Special handling for ``LOADEDMODULES`` variable

HPC Connect Integration
-----------------------

The extension uses hpc_connect's ``remote_subprocess`` backend for:

- Remote job submission
- Process management on remote hosts
- Result collection and transfer
- Error handling and reporting

The hpc_connect backend is configured separately and treated as an external dependency.