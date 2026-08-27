.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Remote Execution
================

The ``canary_dist`` extension implements remote execution through a nested Canary invocation model. This approach enables distributed test execution while maintaining compatibility with Canary's existing job execution framework.

Nested Execution Model
----------------------

The distributed execution system uses a two-level execution model:

1. **Outer Execution**: ``canary dist run`` on submission host
2. **Inner Execution**: ``canary dist exec`` on remote machine

Execution Flow
--------------

1. **Batch Preparation**: Outer execution creates batch workspaces
2. **Remote Invocation**: Outer execution calls ``canary dist exec`` on remote machine
3. **Batch Execution**: Inner execution runs tests using batch-local resources
4. **Result Return**: Inner execution returns results to outer execution
5. **Result Integration**: Outer execution integrates results into workspace

Remote Execution Command
------------------------

The ``canary dist exec`` command handles remote batch execution:

.. code-block:: console

   python3 -m canary dist exec --workspace /path/to/batch/workspace

Command Options
~~~~~~~~~~~~~~~

- ``--workspace DIST_WORKSPACE``: Path to batch workspace (required)
- ``--workers WORKERS``: Number of workers for batch execution

Workspace Structure
-------------------

Each batch workspace contains:

.. code-block:: text

   batch/workspace/
   ├── batch.lock              # Batch configuration
   ├── resource_pool.json      # Batch resource pool
   ├── jobs/                   # Job specifications
   ├── results/                # Test results
   ├── logs/                   # Execution logs
   └── cache/                  # Temporary files

Batch Lock File
~~~~~~~~~~~~~~~

The ``batch.lock`` file contains batch metadata:

.. code-block:: json

   {
     "id": "batch-abc123",
     "session": "session-xyz",
     "workspace": "/path/to/workspace",
     "jobs": ["job1", "job2", "job3"],
     "metadata": {
       "hostname": "host-a",
       "transaction_id": "tx-12345"
     }
   }

Resource Pool File
~~~~~~~~~~~~~~~~~~

The ``resource_pool.json`` file contains the batch-local resource pool:

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

Remote Execution Process
------------------------

1. **Workspace Setup**: Remote execution loads batch workspace
2. **Resource Pool Loading**: Loads batch-local resource pool
3. **Job Discovery**: Discovers jobs in batch workspace
4. **Job Execution**: Executes jobs using local Canary execution
5. **Result Collection**: Gathers test results
6. **Workspace Update**: Updates workspace with results
7. **Cleanup**: Performs post-execution cleanup

HPC Connect Backend
-------------------

The extension uses hpc_connect's ``remote_subprocess`` backend for:

- Remote command execution
- Process management
- Result transfer
- Error handling

Backend Configuration
~~~~~~~~~~~~~~~~~~~~~

The hpc_connect backend must be configured separately:

.. code-block:: python

   import hpc_connect
   hpc_connect.config.export()
   backend = hpc_connect.get_backend("remote_subprocess")

Remote Subprocess Execution
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The remote subprocess backend:

1. **Command Execution**: Runs ``canary dist exec`` on remote machine
2. **Environment Setup**: Configures execution environment
3. **Process Monitoring**: Tracks remote process status
4. **Result Collection**: Gathers output and results
5. **Error Handling**: Manages remote execution failures

Environment Export
------------------

The ``--export`` option controls environment variable propagation:

Export Modes
~~~~~~~~~~~~

1. **Default Mode**: No environment variables exported
2. **ALL Mode**: All environment variables exported
3. **Selective Mode**: Specific variables exported

Export Examples
~~~~~~~~~~~~~~~

Export specific variables:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=MYVAR,OTHER ./tests

Export with specific values:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=MYVAR=value,OTHER=value2 ./tests

Export all variables:

.. code-block:: console

   python3 -m canary dist run --server-url http://pool.example:8000 --export=ALL ./tests

Module Handling
~~~~~~~~~~~~~~~

Special handling for ``LOADEDMODULES`` variable:

- If exported, modules are loaded on remote host
- Module environment is reconstructed
- Module dependencies are respected

Remote Execution Constraints
----------------------------

Single Machine Constraint
~~~~~~~~~~~~~~~~~~~~~~~~~

- Each batch executes on exactly one remote machine
- No multi-node batch execution support
- Resource requirements must fit on single machine

Resource Constraints
~~~~~~~~~~~~~~~~~~~~

- Batch resource requirements must match checked-out resources
- Resource pool is fixed for batch duration
- No dynamic resource adjustment during execution

Execution Constraints
~~~~~~~~~~~~~~~~~~~~~

- Remote execution uses batch-local resource pool
- No access to full distributed pool during execution
- Results must be returned to submission host

Error Handling
--------------

Remote execution handles several error conditions:

Connection Errors
~~~~~~~~~~~~~~~~~

- Network connectivity issues
- Authentication failures
- Remote host unavailable

Execution Errors
~~~~~~~~~~~~~~~~

- Command execution failures
- Process termination errors
- Timeout errors

Resource Errors
~~~~~~~~~~~~~~~

- Resource pool loading failures
- Resource allocation mismatches
- Transaction validation errors

Result Errors
~~~~~~~~~~~~~

- Result collection failures
- Workspace update errors
- Result transfer issues

Debugging Remote Execution
---------------------------

Common remote execution problems and solutions:

Connection Failures
~~~~~~~~~~~~~~~~~~~

**Symptoms**: Connection refused, authentication errors, network timeouts

**Solutions**:

- Verify remote host availability
- Check network connectivity
- Validate authentication credentials
- Review hpc_connect configuration

Execution Failures
~~~~~~~~~~~~~~~~~~

**Symptoms**: Command execution errors, process failures, timeouts

**Solutions**:

- Check remote host resource availability
- Review job resource requirements
- Validate execution environment
- Examine remote execution logs

Resource Mismatches
~~~~~~~~~~~~~~~~~~~

**Symptoms**: Resource pool loading failures, allocation errors

**Solutions**:

- Verify resource pool file format
- Check transaction ID validity
- Validate resource requirements
- Review checkout process

Result Issues
~~~~~~~~~~~~~

**Symptoms**: Missing results, incomplete data, transfer failures

**Solutions**:

- Check workspace permissions
- Review result collection process
- Validate result file formats
- Examine transfer logs

Diagnostic Commands
~~~~~~~~~~~~~~~~~~~

Use these commands to debug remote execution:

.. code-block:: console

   # Check remote host connectivity
   ping host-a
   ssh host-a

   # Test hpc_connect configuration
   python3 -c "import hpc_connect; print(hpc_connect.get_backend('remote_subprocess'))"

   # Run with verbose logging
   python3 -m canary dist run --server-url http://pool.example:8000 --verbose ./tests

   # Test workspace manually
   python3 -m canary dist exec --workspace /path/to/batch/workspace

Performance Considerations
--------------------------

Remote Overhead
~~~~~~~~~~~~~~~

- Network latency affects execution time
- Result transfer adds overhead
- Remote process startup has cost

Batch Size Optimization
~~~~~~~~~~~~~~~~~~~~~~~

- Larger batches reduce remote invocation overhead
- Smaller batches provide better parallelism
- Optimal size depends on test characteristics

Resource Utilization
~~~~~~~~~~~~~~~~~~~~

- Match batch size to machine capacity
- Consider resource diversity across pool
- Balance batch count with available machines

Environment Considerations
---------------------------

Remote Environment
~~~~~~~~~~~~~~~~~~

- Remote execution environment may differ from submission host
- Environment variables must be explicitly exported
- Module environments must be reconstructed

Workspace Requirements
~~~~~~~~~~~~~~~~~~~~~~

- Remote host must have Canary installed
- Workspace directory must be accessible
- Sufficient disk space for results
- Appropriate permissions for execution

Network Requirements
~~~~~~~~~~~~~~~~~~~~

- Network connectivity between submission and remote hosts
- Sufficient bandwidth for result transfer
- Low latency for interactive debugging
- Firewall rules allowing remote execution