.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Batch Workspaces
================

Batch workspaces are the core of Canary's HPC execution model, containing all the metadata, configuration, and results needed for nested batch execution. Understanding batch workspace structure is essential for debugging and troubleshooting HPC executions.

Batch Workspace Location
------------------------

Batch workspaces are created under the Canary cache directory:

.. code-block:: text

   .canary/cache/canary-hpc/batches/<batch-id-prefix>/

**Structure**:

- ``.canary/cache/canary-hpc/``: HPC cache directory
- ``batches/``: Batch workspace directory
- ``<batch-id-prefix>/``: Individual batch workspace (7-character prefix)

**Example**:

.. code-block:: text

   .canary/cache/canary-hpc/batches/abc1234/

Batch Workspace Files
---------------------

batch.lock
~~~~~~~~~~

**Purpose**: Batch metadata and state

**Content**:

- Batch ID and configuration
- Job list and dependencies
- Resource allocation information
- Status and execution state
- Timestamps and metadata

**Format**: JSON

**Example**:

.. code-block:: json

   {
     "batch_id": "abc1234",
     "jobs": ["job1", "job2", "job3"],
     "dependencies": {
       "job2": ["job1"],
       "job3": ["job2"]
     },
     "resources": {
       "cpus": 8,
       "nodes": 2,
       "gpus": 1
     },
     "status": "RUNNING",
     "timestamp": "2024-01-01T00:00:00Z",
     "workspace": "/path/to/workspace"
   }

resource_pool.json
~~~~~~~~~~~~~~~~~~

**Purpose**: Batch-local topology-aware resource pool

**Content**:

- Node definitions and resources
- Resource properties and constraints
- Allocation metadata
- Topology information

**Format**: JSON

**Example**:

.. code-block:: json

   {
     "allow_multinode": false,
     "additional_properties": {
       "source": "batch-local",
       "batch_id": "abc1234"
     },
     "nodes": [
       {
         "id": "batch-node",
         "resources": {
           "cpus": [
             {"id": "0", "slots": 4, "node": "batch-node"},
             {"id": "1", "slots": 4, "node": "batch-node"}
           ],
           "gpus": [
             {"id": "0", "slots": 1, "node": "batch-node", "properties": {"vendor": "UNKNOWN"}}
           ]
         }
       }
     ]
   }

config.json
~~~~~~~~~~~

**Purpose**: Configuration snapshot for nested execution

**Content**:

- Canary configuration
- Batch-specific settings
- Environment information
- Execution parameters

**Format**: JSON

**Example**:

.. code-block:: json

   {
     "config": {
       "backend": "slurm",
       "batch_spec": {
         "layout": "flat",
         "nodes": "same",
         "duration": "30m"
       },
       "resources": {
         "cpus": 8,
         "nodes": 2
       }
     },
     "environment": {
       "CANARY_HPC_BACKEND": "slurm",
       "CANARY_BATCH_ID": "abc1234"
     }
   }

canary-inp.sh
~~~~~~~~~~~~~

**Purpose**: Input script for nested Canary execution

**Content**:

- Nested Canary command
- Batch execution configuration
- Environment setup
- Execution parameters

**Format**: Shell script

**Example**:

.. code-block:: bash

   #!/bin/bash
   # Canary HPC batch input script
   # Batch ID: abc1234
   # Backend: slurm

   export CANARY_BATCH_ID="abc1234"
   export CANARY_HPC_BACKEND="slurm"

   python -m canary -C /path/to/workspace hpc exec \
     --batch-id=abc1234 \
     --backend=slurm \
     --workspace=/path/to/workspace

canary-out.txt
~~~~~~~~~~~~~~

**Purpose**: Output from nested Canary execution

**Content**:

- Console output from batch execution
- Job results and status
- Execution logs
- Error messages

**Format**: Text

procinfo.json
~~~~~~~~~~~~~

**Purpose**: Process information from batch execution

**Content**:

- Process IDs and information
- Execution metadata
- Resource usage
- Timing information

**Format**: JSON (if written by source)

logs/
~~~~~

**Purpose**: Execution logs directory

**Content**:

- Job-specific logs
- Execution logs
- Debug logs
- Timestamps

**Format**: Text files

results/
~~~~~~~~

**Purpose**: Job results directory

**Content**:

- Job output files
- Result files
- Artifacts
- Metadata

**Format**: Various

Batch Workspace Creation
------------------------

**Creation Process**:

1. Batch ID generated (7-character prefix)
2. Workspace directory created
3. Metadata files written
4. Resource pool configured
5. Configuration snapshot saved
6. Input script generated
7. Workspace prepared for submission

**Nested Execution**:

1. Scheduler job starts
2. Input script executed
3. Nested Canary invoked
4. Batch-local resource pool loaded
5. Jobs executed with allocated resources
6. Results saved to workspace
7. Output captured
8. Workspace finalized

Batch Workspace Lifecycle
--------------------------

**Creation**:

- ``canary hpc run`` creates batch workspaces
- Workspaces prepared for submission
- Metadata and configuration saved

**Submission**:

- Batch submitted to scheduler
- Workspace path passed to scheduler
- Input script configured for execution

**Execution**:

- Scheduler starts job
- Input script executes
- Nested Canary runs in workspace
- Jobs execute with batch resources

**Completion**:

- Results saved to workspace
- Status updated
- Output files written
- Workspace finalized

**Cleanup**:

- Workspace retained for debugging
- Can be manually removed if needed
- Retention policy configurable

Batch Workspace Examples
------------------------

**Workspace Inspection**:

.. code-block:: console

   # List batch workspaces
   ls .canary/cache/canary-hpc/batches/

   # Inspect specific workspace
   ls .canary/cache/canary-hpc/batches/abc1234/

   # Read batch metadata
   cat .canary/cache/canary-hpc/batches/abc1234/batch.lock

   # Check resource pool
   cat .canary/cache/canary-hpc/batches/abc1234/resource_pool.json

**Workspace Debugging**:

.. code-block:: console

   # Check batch status
   python3 -m canary hpc log abc1234

   # Inspect batch configuration
   cat .canary/cache/canary-hpc/batches/abc1234/config.json

   # Review batch output
   cat .canary/cache/canary-hpc/batches/abc1234/canary-out.txt

   # Check job results
   ls .canary/cache/canary-hpc/batches/abc1234/results/

Batch Workspace Management
---------------------------

**Manual Inspection**:

.. code-block:: console

   # Find batch workspaces
   find .canary/cache/canary-hpc/batches/ -type d

   # Check workspace contents
   tree .canary/cache/canary-hpc/batches/abc1234/

   # Read specific files
   cat .canary/cache/canary-hpc/batches/abc1234/batch.lock | jq .

**Manual Cleanup**:

.. code-block:: console

   # Remove specific workspace
   rm -rf .canary/cache/canary-hpc/batches/abc1234/

   # Remove all workspaces
   rm -rf .canary/cache/canary-hpc/batches/*

   # Remove HPC cache
   rm -rf .canary/cache/canary-hpc/

Batch Workspace Best Practices
------------------------------

1. **Inspection**: Regularly inspect workspaces for debugging
2. **Retention**: Configure appropriate retention policies
3. **Cleanup**: Remove old workspaces to save space
4. **Backup**: Backup important workspace data
5. **Documentation**: Document workspace structure and contents
6. **Monitoring**: Monitor workspace creation and usage
7. **Validation**: Validate workspace contents before submission