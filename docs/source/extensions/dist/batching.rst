.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Batching
========

The ``canary_dist`` extension uses batching to efficiently execute tests across distributed resources. Batching groups individual test jobs into larger units that can be executed together on remote machines, improving resource utilization and reducing overhead.

Why Batching is Used
--------------------

Batching provides several key benefits for distributed execution:

1. **Reduced Overhead**: Minimizes the number of remote submissions and resource checkouts
2. **Improved Utilization**: Better matches test workloads to machine capacities
3. **Dependency Management**: Groups dependent jobs together for efficient execution
4. **Resource Efficiency**: Reduces resource fragmentation across the pool
5. **Scheduling Flexibility**: Allows control over batch size and duration

Batch Formation Process
-----------------------

The batch formation process involves several steps:

1. **Job Collection**: Gather all eligible test jobs
2. **Resource Analysis**: Determine resource requirements for each job
3. **Dependency Analysis**: Identify job dependencies and ordering constraints
4. **Batch Grouping**: Group jobs into batches based on configuration
5. **Resource Validation**: Ensure batches fit within available resources
6. **Batch Optimization**: Optimize batch composition for efficiency

Batch Configuration Options
---------------------------

Batch Width
~~~~~~~~~~~

The ``--batch-width`` option controls the CPU width of each batch:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 16 ./tests

- **Default**: 8 CPUs
- **Effect**: Determines maximum CPU resources available to each batch
- **Constraint**: Individual jobs requiring more CPUs than batch width are excluded

Batch Count
~~~~~~~~~~~

The ``--batch-count`` option specifies the exact number of batches to create:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --batch-count 4 ./tests

- **Default**: Auto (determined by batching algorithm)
- **Effect**: Creates exactly the specified number of batches
- **Constraint**: Mutually exclusive with ``--batch-duration``

Batch Duration
~~~~~~~~~~~~~~

The ``--batch-duration`` option controls the approximate duration of each batch:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --batch-duration 30m ./tests
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-duration 2h ./tests

- **Default**: 10 minutes
- **Format**: Supports Go duration format (e.g., ``30m``, ``2h``, ``1h30m``)
- **Effect**: Groups jobs to approximate the specified duration
- **Constraint**: Mutually exclusive with ``--batch-count``

Exact Estimation
~~~~~~~~~~~~~~~~

The ``--batch-exact-estimate`` option enables precise runtime estimation:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --batch-exact-estimate ./tests

- **Default**: False (uses cheap estimates)
- **Effect**: Runs exact scheduler simulation for each final batch
- **Performance**: Slower for very large test suites
- **Accuracy**: Provides more accurate runtime estimates

Batch Formation Algorithm
--------------------------

The batch formation algorithm considers multiple factors:

Resource Requirements
~~~~~~~~~~~~~~~~~~~~~

Each job's resource requirements are analyzed:

- CPU requirements
- GPU requirements (if applicable)
- Other custom resource requirements
- Memory and storage constraints

Dependency Constraints
~~~~~~~~~~~~~~~~~~~~~~

Job dependencies are respected during batching:

- Jobs with dependencies are grouped together when possible
- Dependency chains are preserved across batches
- Circular dependencies are detected and handled

Resource Capacity
~~~~~~~~~~~~~~~~~

Available resource capacity is determined by:

- Maximum per-machine capacity from eligible machines
- Batch width constraints
- Resource type availability
- Machine-specific resource limits

Scheduling Constraints
~~~~~~~~~~~~~~~~~~~~~~

The batching algorithm enforces several constraints:

1. **Single-Node Constraint**: All jobs in a batch must fit on a single machine
2. **Resource Fit**: Batch resource requirements must fit within machine capacity
3. **Dependency Preservation**: Job dependencies must be respected
4. **Duration Targets**: Batches should approximate target duration (when specified)

Batch Composition
-----------------

A typical batch contains:

- **Jobs**: Collection of test jobs to execute
- **Resources**: Allocated resources for the batch
- **Metadata**: Batch identification and configuration
- **Workspace**: Local workspace for batch execution
- **Dependencies**: Information about job dependencies

Example Batch Structure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
     "id": "batch-abc123",
     "jobs": ["job1", "job2", "job3"],
     "cpus": 8,
     "resources": {
       "cpus": [{"id": "0", "slots": 4}, {"id": "1", "slots": 4}],
       "gpus": [{"id": "0", "slots": 1}]
     },
     "metadata": {
       "hostname": "host-a",
       "transaction_id": "tx-12345",
       "batch_width": 8,
       "estimated_duration": 420
     }
   }

Batch Execution
---------------

Once formed, batches are executed through the following process:

1. **Resource Checkout**: Reserve resources from pool server
2. **Workspace Creation**: Create local workspace for batch
3. **Remote Submission**: Submit batch to remote machine
4. **Remote Execution**: Execute tests on remote machine
5. **Result Collection**: Gather test results
6. **Resource Checkin**: Release resources back to pool

Batch Workspace
~~~~~~~~~~~~~~~~

Each batch has its own workspace containing:

- Batch configuration and metadata
- Resource pool information
- Job specifications and dependencies
- Execution logs and results
- Temporary files and artifacts

Resource Pool File
~~~~~~~~~~~~~~~~~~~~~~

The batch workspace contains a ``resource_pool.json`` file with:

.. code-block:: json

   {
     "resource_pool": {
       "allow_multinode": false,
       "additional_properties": {
         "source": "distributed-checkout",
         "hostname": "host-a",
         "transaction_id": "tx-12345"
       },
       "nodes": [
         {
           "id": "host-a",
           "resources": {
             "cpus": [{"id": "0", "slots": 4}, {"id": "1", "slots": 4}]
           }
         }
       ]
     }
   }

Batch Dependencies
------------------

The batching system handles job dependencies through:

Dependency Analysis
~~~~~~~~~~~~~~~~~~~~~~

Dependencies are analyzed to:

- Identify dependency chains and graphs
- Group dependent jobs together when possible
- Preserve execution order across batches
- Detect and handle circular dependencies

Dependency-Aware Batching
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The algorithm uses dependency information to:

- Create batches that respect dependency order
- Minimize cross-batch dependencies
- Optimize batch composition for dependency-heavy workloads
- Handle complex dependency graphs

Dependency Graph Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   Job A → Job B → Job C
         ↓
   Job D → Job E

This might result in batches:

- Batch 1: Job A, Job D
- Batch 2: Job B, Job E
- Batch 3: Job C

Batch Limitations
-----------------

The batching system has several limitations:

Resource Constraints
~~~~~~~~~~~~~~~~~~~~~~~

- Batches limited by single machine capacity
- No support for multi-node batches
- Resource requirements must fit within batch width

Dependency Constraints
~~~~~~~~~~~~~~~~~~~~~~~~

- Complex dependency graphs may limit batching efficiency
- Circular dependencies can prevent batch formation
- Cross-batch dependencies may reduce parallelism

Algorithm Constraints
~~~~~~~~~~~~~~~~~~~~~~~~

- Exact estimation slower for very large suites
- Batch count and duration are mutually exclusive
- Batch width must be positive integer

Performance Considerations
--------------------------

Batch Size Trade-offs
~~~~~~~~~~~~~~~~~~~~~

- **Small batches**: More parallelism, higher overhead
- **Large batches**: Better utilization, less parallelism
- **Optimal size**: Depends on test characteristics and pool size

Estimation Accuracy
~~~~~~~~~~~~~~~~~~~~~~

- Cheap estimates: Fast but less accurate
- Exact estimates: More accurate but slower
- Choose based on suite size and accuracy needs

Resource Utilization
~~~~~~~~~~~~~~~~~~~~~~~

- Batch width should match typical machine capacity
- Consider resource diversity across pool machines
- Balance batch size with available machine count

Debugging Batching Issues
--------------------------

Common batching problems and solutions:

Insufficient Resources
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: No batches formed, resource allocation failures

**Solutions**:

- Check pool status with ``canary dist status``
- Reduce batch width requirements
- Filter machines with appropriate tags
- Ensure machines are online and available

Dependency Issues
~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Batches with many cross-dependencies, poor parallelism

**Solutions**:

- Review job dependency specifications
- Simplify complex dependency graphs
- Use smaller batches for dependency-heavy workloads

Batch Formation Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: No batches created, batching algorithm errors

**Solutions**:

- Check job resource requirements
- Verify batch width is appropriate
- Ensure jobs are eligible for distributed execution
- Review batching constraints and limits

Diagnostic Commands
~~~~~~~~~~~~~~~~~~~~~~

Use these commands to debug batching issues:

.. code-block:: console

   # Check pool status and available resources
   python3 -m canary dist status --server-url http://pool.example:8000

   # Run with verbose logging to see batching details
   python3 -m canary dist run --server-url http://pool.example:8000 --verbose ./tests

   # Test with different batching parameters
   python3 -m canary dist run --server-url http://pool.example:8000 --batch-width 4 ./tests