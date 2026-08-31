.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Runtime Environment
===================

The GPU vendor extensions configure runtime environment variables for jobs that have been allocated GPU resources. This enables jobs to access the specific GPU devices assigned to them.

Environment Variable Configuration
-----------------------------------

The extensions set vendor-specific environment variables through the ``canary_runteststart`` hook, which is called before each job execution.

Configuration Process
---------------------

1. **Job Resource Allocation**: Canary allocates GPU resources to job
2. **Hook Invocation**: ``canary_runteststart`` called before job execution
3. **GPU Selection**: Extension filters allocated GPUs by vendor compatibility
4. **Environment Setup**: Extension sets appropriate environment variables
5. **Job Execution**: Job runs with configured environment

NVIDIA Environment Configuration
--------------------------------

**Variable**: ``CUDA_VISIBLE_DEVICES``

**Purpose**: Controls which GPU devices are visible to CUDA applications

**Format**: Comma-separated list of local GPU device IDs

**Example**:

.. code-block:: text

   CUDA_VISIBLE_DEVICES=0,1,2

**Behavior**:

- Sets ``CUDA_VISIBLE_DEVICES`` to allocated GPU local IDs
- Deduplicates IDs while preserving order
- Only sets if user hasn't already set the variable
- Only sets if NVIDIA-compatible GPUs are allocated

**Selection Logic**:

.. code-block:: python

   def _nvidia_gpus(case: canary.Job) -> list[dict[str, Any]]:
       gpus = case.resources.get("gpus", [])
       nvidia_gpus = []
       for gpu in gpus:
           vendor = str(gpu.get("properties", {}).get("vendor", "")).upper()
           if vendor in {"NVIDIA", "UNKNOWN", ""}:
               nvidia_gpus.append(gpu)
       return nvidia_gpus

**Vendor Compatibility**: Accepts ``NVIDIA``, ``UNKNOWN``, or empty vendor values

AMD Environment Configuration
-----------------------------

**Variables**:

- ``HIP_VISIBLE_DEVICES``
- ``ROCR_VISIBLE_DEVICES``
- ``CUDA_VISIBLE_DEVICES``

**Purpose**: Controls which GPU devices are visible to HIP, ROCr, and CUDA applications

**Format**: Comma-separated list of local GPU device IDs (same value for all variables)

**Example**:

.. code-block:: text

   HIP_VISIBLE_DEVICES=0,1
   ROCR_VISIBLE_DEVICES=0,1
   CUDA_VISIBLE_DEVICES=0,1

**Behavior**:

- Sets all three variables to the same value
- Uses allocated GPU local IDs
- Deduplicates IDs while preserving order
- Only sets if user hasn't already set any of the variables
- Only sets if AMD-compatible GPUs are allocated

**Selection Logic**:

.. code-block:: python

   def _amd_gpus(case: canary.Job) -> list[dict[str, Any]]:
       gpus = case.resources.get("gpus", [])
       amd_gpus = []
       for gpu in gpus:
           vendor = str(gpu.get("properties", {}).get("vendor", "")).upper()
           if vendor in {"AMD", "ROCM"}:
               amd_gpus.append(gpu)
       return amd_gpus

**Vendor Compatibility**: Only accepts ``AMD`` or ``ROCM`` vendor values

User Override Behavior
----------------------

Both extensions respect user-set environment variables:

**NVIDIA**:

.. code-block:: python

   if "CUDA_VISIBLE_DEVICES" in case.variables:
       return  # User override: don't override

**AMD**:

.. code-block:: python

   if any(var in case.variables for var in _AMD_VISIBLE_DEVICES_VARIABLES):
       return  # User override: don't override

**Effect**:

- User-set variables take precedence
- Extensions do not override user configurations
- Enables manual environment control when needed

Multi-Node Environment Handling
-------------------------------

Both extensions handle multi-node GPU allocations:

.. code-block:: python

   # Preserve order while removing duplicates
   visible = ",".join(dict.fromkeys(local_ids))

**Importance**:

- Multiple nodes may contribute the same local GPU ID (e.g., GPU 0 on each node)
- Deduplication prevents duplicate device visibility
- Order preservation maintains allocation order

Environment Variable Examples
-----------------------------

Single GPU
~~~~~~~~~~

**Allocation**: 1 GPU with local ID 0

**NVIDIA**:

.. code-block:: text

   CUDA_VISIBLE_DEVICES=0

**AMD**:

.. code-block:: text

   HIP_VISIBLE_DEVICES=0
   ROCR_VISIBLE_DEVICES=0
   CUDA_VISIBLE_DEVICES=0

Multiple GPUs
~~~~~~~~~~~~~

**Allocation**: 3 GPUs with local IDs 0, 1, 2

**NVIDIA**:

.. code-block:: text

   CUDA_VISIBLE_DEVICES=0,1,2

**AMD**:

.. code-block:: text

   HIP_VISIBLE_DEVICES=0,1,2
   ROCR_VISIBLE_DEVICES=0,1,2
   CUDA_VISIBLE_DEVICES=0,1,2

Multi-Node with Duplicate IDs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Allocation**: GPU 0 from node A, GPU 0 from node B, GPU 1 from node A

**Result**:

.. code-block:: text

   CUDA_VISIBLE_DEVICES=0,1  # Deduplicated, order preserved

Environment Variable Usage
--------------------------

Applications use these environment variables to:

1. **Device Selection**: Choose which GPU devices to use
2. **Resource Management**: Limit GPU resource usage
3. **Compatibility**: Ensure correct vendor runtime is used
4. **Isolation**: Prevent interference between jobs

Reading Environment Variables
-----------------------------

Jobs can read the configured environment variables:

**Python**:

.. code-block:: python

   import os

   # NVIDIA
   cuda_devices = os.environ.get("CUDA_VISIBLE_DEVICES", "")
   print(f"Visible CUDA devices: {cuda_devices}")

   # AMD
   hip_devices = os.environ.get("HIP_VISIBLE_DEVICES", "")
   rocr_devices = os.environ.get("ROCR_VISIBLE_DEVICES", "")
   print(f"Visible HIP devices: {hip_devices}")
   print(f"Visible ROCR devices: {rocr_devices}")

**Bash**:

.. code-block:: bash

   # Check visible devices
   echo "CUDA devices: $CUDA_VISIBLE_DEVICES"
   echo "HIP devices: $HIP_VISIBLE_DEVICES"
   echo "ROCR devices: $ROCR_VISIBLE_DEVICES"

Environment Variable Behavior
-----------------------------

Variable Not Set
~~~~~~~~~~~~~~~~

**Conditions**:

- No GPU resources allocated to job
- No compatible GPU resources allocated
- User has already set the variable

**Effect**: Environment variable is not modified

Empty Variable
~~~~~~~~~~~~~~

**Conditions**:

- GPU resources allocated but selection logic returns empty list
- All allocated GPUs filtered out by vendor compatibility

**Effect**: Environment variable is not set

Debugging Environment Variables
--------------------------------

To debug environment variable configuration:

.. code-block:: console

   # Run with verbose logging
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

   # Check job environment
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/env_check.py

   # Test specific GPU allocation
   python3 -m canary run --gpu-backend=amd -p "gpus=2,vendor=AMD" tests/gpu_test.py

Environment Variable Limitations
---------------------------------

1. **User Override Priority**: User-set variables always take precedence
2. **Vendor Compatibility**: Only sets variables for compatible GPUs
3. **Local Device IDs**: Uses node-local IDs, not global IDs
4. **No Validation**: Does not validate device existence
5. **No Error Handling**: Silently skips if conditions not met
6. **Job-Specific**: Variables set per-job, not globally
7. **Process-Specific**: Only affects the job process

Best Practices
--------------

1. **Respect User Overrides**: Don't override user-set variables
2. **Check Variable Presence**: Verify variables are set before using
3. **Handle Missing Variables**: Provide fallback behavior
4. **Use Vendor-Specific Variables**: Use appropriate variables for each vendor
5. **Test Environment**: Verify environment in test setup
6. **Document Requirements**: Specify required environment variables
7. **Consider Multi-Node**: Handle duplicate local IDs appropriately