.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Resource Pool Server
====================

The distributed resource pool server is an external service that manages the pool of machines available for distributed test execution. The ``canary_dist`` extension communicates with this server to discover resources, check out machines for batch execution, and manage resource allocations.

Server Configuration
--------------------

Server URL
~~~~~~~~~~

The server URL can be specified in several ways:

1. **Command Line**: ``--server-url http://pool.example:8000``
2. **Environment Variable**: ``CANARY_DIST_SERVER_URL``
3. **Configuration**: Can be set in Canary configuration files

Example server URL formats:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 ./tests
   python3 -m canary dist run --server-url pool.example:8000 ./tests

Server State
------------

The server maintains state about the distributed resource pool including:

Machine Information
~~~~~~~~~~~~~~~~~~~

Each machine in the pool has:

- ``hostname``: Unique machine identifier
- ``state``: ``"online"`` or ``"offline"``
- ``tags``: List of machine tags for filtering
- ``groups``: List of machine groups for filtering
- ``resources``: Available resource types and counts

Resource Information
~~~~~~~~~~~~~~~~~~~~

Resources are tracked per machine with:

- Resource type (``"cpus"``, ``"gpus"``, etc.)
- Resource instances with ``id`` and ``slots``
- Total available slots per resource type

Server Endpoints
----------------

The server exposes several HTTP endpoints used by Canary:

Status Endpoint
~~~~~~~~~~~~~~~

**Endpoint**: ``GET /status``

**Purpose**: Retrieve current pool state

**Response**: JSON containing all machines and their resources

**Example Response**:

.. code-block:: json

   {
     "database": {
       "machines": [
         {
           "hostname": "host-a",
           "state": "online",
           "tags": ["gpu", "fast"],
           "groups": ["production"],
           "resources": {
             "cpus": [
               {"id": "0", "slots": 4},
               {"id": "1", "slots": 4}
             ],
             "gpus": [
               {"id": "0", "slots": 1}
             ]
           }
         }
       ]
     }
   }

Accommodates Endpoint
~~~~~~~~~~~~~~~~~~~~~

**Endpoint**: ``POST /accommodates``

**Purpose**: Check if pool can accommodate a resource request

**Request**: JSON with resource requirements

**Response**: JSON with ``accommodates`` boolean and ``reason`` string

**Example Request**:

.. code-block:: json

   {
     "resources": [
       {"type": "cpus", "slots": 8}
     ]
   }

Checkout Endpoint
~~~~~~~~~~~~~~~~~

**Endpoint**: ``POST /checkout``

**Purpose**: Reserve resources for batch execution

**Request**: JSON with resource requirements, timeout, tags, and groups

**Response**: JSON with checkout success, hostname, transaction ID, and resources

**Example Response**:

.. code-block:: json

   {
     "success": true,
     "hostname": "host-a",
     "transaction_id": "tx-12345",
     "resources": {
       "cpus": [
         {"id": "0", "slots": 4},
         {"id": "1", "slots": 4}
       ]
     }
   }

Checkin Endpoint
~~~~~~~~~~~~~~~~

**Endpoint**: ``POST /checkin``

**Purpose**: Release reserved resources back to pool

**Request**: JSON with transaction ID

**Response**: JSON with checkin success status

RX (Health Check) Endpoint
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Endpoint**: ``POST /rx``

**Purpose**: Health check and cleanup of expired checkouts

**Request**: No data required

**Response**: JSON with health check status

Machine Eligibility
-------------------

The Canary adapter filters machines based on several criteria:

State Filtering
~~~~~~~~~~~~~~~

Only machines with ``state`` = ``"online"`` are considered eligible.

Tag Filtering
~~~~~~~~~~~~~

Machines can be filtered by tags using the ``--tags`` option:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --tags gpu,fast ./tests

This requires machines to have ALL specified tags.

Group Filtering
~~~~~~~~~~~~~~~

Machines can be filtered by groups (not yet fully implemented in current version).

Resource Discovery
------------------

The adapter discovers resources through the following process:

1. Query server for current state via ``/status`` endpoint
2. Filter machines by state, tags, and groups
3. Aggregate resource counts per machine
4. Calculate maximum available capacity per resource type
5. Create Canary resource pool with one node per eligible machine

Resource Translation
--------------------

The adapter translates server resources to Canary's model:

1. **Flat to Topology-Aware**: Server provides flat resource lists, adapter creates node-based topology
2. **Node Identity**: Each machine becomes a Canary node with the machine hostname as node ID
3. **Resource Attachment**: Server resource instances are attached to their respective nodes
4. **Capacity Calculation**: Maximum per-machine capacity determined for scheduling

Example Translation
~~~~~~~~~~~~~~~~~~~

Server resource:

.. code-block:: json

   {
     "hostname": "host-a",
     "resources": {
       "cpus": [{"id": "0", "slots": 4}]
     }
   }

Becomes Canary node:

.. code-block:: json

   {
     "id": "host-a",
     "resources": {
       "cpus": [{"id": "0", "slots": 4, "node": "host-a"}]
     }
   }

Error Handling
--------------

The adapter handles various server error conditions:

- **Unavailable Server**: Connection errors and timeouts
- **Malformed Responses**: Invalid JSON or unexpected data formats
- **Checkout Failures**: Insufficient resources or server errors
- **Checkin Failures**: Transaction not found or already released
- **Health Check Failures**: Server cleanup issues

Error conditions are logged and appropriate exceptions are raised to provide diagnostic information to users.