.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Resources
=========

The ``canary_dist`` extension manages resource allocation and utilization across the distributed pool. This includes CPU, GPU, and other resource types provided by the pool server.

Resource Types
--------------

The distributed execution system supports several resource types:

CPU Resources
~~~~~~~~~~~~~

- **Type**: ``"cpus"``
- **Description**: Processing units for test execution
- **Attributes**: ``id``, ``slots``, ``node``
- **Usage**: Primary resource for most test execution

GPU Resources
~~~~~~~~~~~~~

- **Type**: ``"gpus"``
- **Description**: Graphics processing units for specialized workloads
- **Attributes**: ``id``, ``slots``, ``node``
- **Usage**: Accelerated computing, GPU-specific tests

Custom Resources
~~~~~~~~~~~~~~~~

- **Type**: Custom resource types defined by pool server
- **Description**: Specialized resources for specific workloads
- **Attributes**: Type-specific attributes
- **Usage**: Domain-specific resource requirements

Resource Representation
-----------------------

Server-Side Representation
~~~~~~~~~~~~~~~~~~~~~~~~~~

The pool server provides flat resource lists:

.. code-block:: json

   {
     "hostname": "host-a",
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

Canary-Side Representation
~~~~~~~~~~~~~~~~~~~~~~~~~~

The adapter translates to Canary's node-based model:

.. code-block:: json

   {
     "id": "host-a",
     "resources": {
       "cpus": [
         {"id": "0", "slots": 4, "node": "host-a"},
         {"id": "1", "slots": 4, "node": "host-a"}
       ],
       "gpus": [
         {"id": "0", "slots": 1, "node": "host-a"}
       ]
     }
   }

Resource Allocation
-------------------

Resource Checkout
~~~~~~~~~~~~~~~~~

The checkout process:

1. **Request**: Send resource requirements to server
2. **Validation**: Server validates resource availability
3. **Reservation**: Server reserves resources and creates transaction
4. **Response**: Server returns allocation with transaction ID

Checkout Example
~~~~~~~~~~~~~~~~

Request:

.. code-block:: json

   {
     "resources": [
       {"type": "cpus", "slots": 8}
     ],
     "timeout": 1800,
     "tags": ["gpu"],
     "groups": null
   }


Response:

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

Resource Checkin
~~~~~~~~~~~~~~~~

The checkin process:

1. **Request**: Send transaction ID to server
2. **Validation**: Server validates transaction
3. **Release**: Server releases reserved resources
4. **Response**: Server confirms successful checkin

Resource Capacity
-----------------

Capacity Calculation
~~~~~~~~~~~~~~~~~~~~

The adapter calculates maximum capacity:

1. **Per-Machine Capacity**: Determine capacity for each eligible machine
2. **Per-Resource Maximum**: Find maximum capacity across all machines
3. **Overall Capacity**: Combine capacities for scheduling

Capacity Example
~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "cpus": 16,
     "gpus": 4,
     "memory": 128
   }

Resource Constraints
--------------------

Single-Node Constraint
~~~~~~~~~~~~~~~~~~~~~~

- **Requirement**: All resources in a batch must fit on a single machine
- **Effect**: ``allow_multinode = False`` in resource pool
- **Implication**: No multi-node job support

Resource Fit Constraint
~~~~~~~~~~~~~~~~~~~~~~~

- **Requirement**: Batch resource requirements must fit within machine capacity
- **Effect**: Jobs exceeding single-machine capacity are excluded
- **Implication**: Large jobs may be masked from execution

Resource Type Constraint
~~~~~~~~~~~~~~~~~~~~~~~~

- **Requirement**: Requested resource types must be available on machines
- **Effect**: Machines without required resources are filtered out
- **Implication**: Resource-specific tags may be needed

Resource Management
-------------------

Resource Pool
~~~~~~~~~~~~~

The resource pool contains:

.. code-block:: json

   {
     "allow_multinode": false,
     "additional_properties": {
       "source": "canary-dist",
       "server_url": "http://pool.example:8000"
     },
     "nodes": [
       {
         "id": "host-a",
         "resources": {
           "cpus": [{"id": "0", "slots": 4, "node": "host-a"}],
           "gpus": [{"id": "0", "slots": 1, "node": "host-a"}]
         },
         "additional_properties": {
           "distributed": {
             "state": "online",
             "tags": ["gpu", "fast"],
             "groups": ["production"]
           }
         }
       }
     ]
   }

Resource Allocation Metadata
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Allocation metadata includes:

- ``source``: ``"canary-dist"``
- ``server_url``: Pool server location
- ``hostname``: Remote machine hostname
- ``transaction_id``: Unique transaction identifier

Resource Utilization
--------------------

Resource utilization is tracked through:

- **Checkout Tracking**: Transaction IDs track active allocations
- **Checkin Tracking**: Released resources are tracked
- **Health Monitoring**: Server cleans up expired transactions
- **Capacity Monitoring**: Available capacity is continuously updated

Resource Errors
---------------

Common resource errors:

Insufficient Resources
~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Checkout failures, allocation errors

**Causes**:

- Not enough machines available
- Insufficient resource capacity
- Resource fragmentation
- Machine filtering too restrictive

**Solutions**:

- Check pool status
- Adjust machine tags
- Reduce batch requirements
- Add more machines to pool

Resource Checkout Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Checkout errors, transaction failures

**Causes**:

- Server communication issues
- Invalid resource requests
- Transaction conflicts
- Server-side errors

**Solutions**:

- Verify server connectivity
- Check resource request validity
- Review transaction logs
- Contact server administrator

Resource Checkin Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Checkin errors, resource leakage

**Causes**:

- Invalid transaction IDs
- Already released transactions
- Server communication issues
- Server-side errors

**Solutions**:

- Verify transaction ID validity
- Check transaction status
- Review server logs
- Contact server administrator

Resource Accommodation Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Accommodation check failures

**Causes**:

- Insufficient resources
- Invalid resource requests
- Machine eligibility issues
- Server-side constraints

**Solutions**:

- Check resource availability
- Review resource requirements
- Adjust machine filtering
- Contact server administrator

Resource Debugging
------------------

Debug resource issues:

.. code-block:: console

   # Check pool status and available resources
   python3 -m canary dist status --server-url http://pool.example:8000

   # Test resource accommodation
   # (Internal accommodation checks during batch formation)

   # Check resource pool configuration
   python3 -m canary dist run --server-url http://pool.example:8000 --verbose ./tests

   # Review server logs
   # (Server-specific logging location)

Resource Best Practices
-----------------------

Efficient Resource Utilization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Match batch width to typical machine capacity
- Use appropriate machine tags for workloads
- Balance batch size with available resources
- Monitor resource utilization patterns

Resource Constraint Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Understand single-node constraints
- Design tests for single-machine execution
- Avoid multi-node dependencies
- Use appropriate resource requests

Resource Monitoring
~~~~~~~~~~~~~~~~~~~

- Regularly check pool status
- Monitor resource utilization trends
- Track allocation patterns
- Identify resource bottlenecks

Resource Planning
~~~~~~~~~~~~~~~~~

- Plan resource requirements for test suites
- Estimate resource needs for different workloads
- Allocate appropriate machine types
- Consider resource diversity across pool

Resource Limitations
--------------------

The resource management system has several limitations:

- No dynamic resource adjustment during execution
- No resource overcommitment support
- Limited multi-resource type coordination
- No resource priority or preemption
- Basic resource type support only

These limitations should be considered when designing distributed test workloads.
