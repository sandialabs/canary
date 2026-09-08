.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

AMD Runtime Environment
========================

``canary_amd`` configures runtime environment variables for jobs that have been allocated AMD GPU
resources. This enables jobs to access the specific GPU devices assigned to them.

Environment Variable Configuration
------------------------------------

The extension sets ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and ``CUDA_VISIBLE_DEVICES``
through the ``canary_runteststart`` hook, which is called before each job execution.

Configuration Process
---------------------

1. **Job Resource Allocation**: Canary allocates GPU resources to the job
2. **Hook Invocation**: ``canary_runteststart`` is called before job execution
3. **GPU Selection**: Extension filters allocated GPUs by AMD/ROCM vendor compatibility
4. **Environment Setup**: Extension sets all three visible-devices variables
5. **Job Execution**: Job runs with the configured environment

AMD Environment Configuration
------------------------------

**Variables**:

- ``HIP_VISIBLE_DEVICES``
- ``ROCR_VISIBLE_DEVICES``
- ``CUDA_VISIBLE_DEVICES``

**Purpose**: Controls which GPU devices are visible to HIP, ROCr, and CUDA (via ROCm) applications

**Format**: Comma-separated list of local GPU device IDs (same value for all three variables)

**Example**:

.. code-block:: text

   HIP_VISIBLE_DEVICES=0,1
   ROCR_VISIBLE_DEVICES=0,1
   CUDA_VISIBLE_DEVICES=0,1

**Behavior**:

- Sets all three variables to the same comma-separated value
- Uses allocated GPU local IDs
- Deduplicates IDs while preserving order
- Only sets variables if the user has not already set any of them
- Only sets variables if AMD-compatible GPUs are allocated

**Visible Device Variables**:

.. code-block:: python

   _AMD_VISIBLE_DEVICES_VARIABLES = (
       "HIP_VISIBLE_DEVICES",
       "ROCR_VISIBLE_DEVICES",
       "CUDA_VISIBLE_DEVICES",
   )

**Selection Logic**:

.. code-block:: python

   def _amd_gpus(case: canary.Job) -> list[dict[str, Any]]:
       resources = getattr(case, "resources", None)
       if not isinstance(resources, dict):
           return []

       gpus = resources.get("gpus", [])
       if not isinstance(gpus, list):
           return []

       amd_gpus = []
       for gpu in gpus:
           if not isinstance(gpu, dict):
               return []

           if "id" not in gpu:
               return []

           properties = gpu.get("properties", {})
           if not isinstance(properties, dict):
               properties = {}

           vendor = str(properties.get("vendor", "")).upper()

           # Unlike the NVIDIA hook, do not claim UNKNOWN devices here.
           # UNKNOWN resources are allowed to fall through to NVIDIA handling.
           if vendor not in {"AMD", "ROCM"}:
               return []

           amd_gpus.append(gpu)

       return amd_gpus

**Vendor Compatibility**: Accepts ``AMD`` or ``ROCM`` vendor values only.
Rejects ``NVIDIA``, ``UNKNOWN``, empty string, and any other vendor values.

User Override Behavior
----------------------

The extension respects user-set environment variables:

.. code-block:: python

   if any(var in case.variables for var in _AMD_VISIBLE_DEVICES_VARIABLES):
       return  # User override: don't override

**Effect**:

- If **any** of ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, or ``CUDA_VISIBLE_DEVICES``
  is already set in the job variables, the extension does not set any of them
- User configuration takes precedence over automatic configuration
- Enables manual environment control when needed

Multi-Node Environment Handling
--------------------------------

The extension handles multi-node GPU allocations:

.. code-block:: python

   # Preserve order while removing duplicates
   visible = ",".join(dict.fromkeys(local_ids))

**Importance**:

- Multiple nodes may contribute the same local GPU ID (e.g., GPU 0 on each node)
- Deduplication prevents duplicate device entries
- Order preservation maintains allocation order

Environment Variable Examples
------------------------------

Single GPU
~~~~~~~~~~

**Allocation**: 1 GPU with local ID 0

.. code-block:: text

   HIP_VISIBLE_DEVICES=0
   ROCR_VISIBLE_DEVICES=0
   CUDA_VISIBLE_DEVICES=0

Multiple GPUs
~~~~~~~~~~~~~

**Allocation**: 3 GPUs with local IDs 0, 1, 2

.. code-block:: text

   HIP_VISIBLE_DEVICES=0,1,2
   ROCR_VISIBLE_DEVICES=0,1,2
   CUDA_VISIBLE_DEVICES=0,1,2

Multi-Node with Duplicate IDs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Allocation**: GPU 0 from node A, GPU 0 from node B, GPU 1 from node A

**Result**:

.. code-block:: text

   HIP_VISIBLE_DEVICES=0,1   # Deduplicated, order preserved
   ROCR_VISIBLE_DEVICES=0,1
   CUDA_VISIBLE_DEVICES=0,1

Reading Environment Variables
------------------------------

Jobs can read the configured environment variables:

**Python**:

.. code-block:: python

   import os

   hip_devices = os.environ.get("HIP_VISIBLE_DEVICES", "")
   rocr_devices = os.environ.get("ROCR_VISIBLE_DEVICES", "")
   cuda_devices = os.environ.get("CUDA_VISIBLE_DEVICES", "")

   if hip_devices:
       print(f"Visible HIP devices: {hip_devices}")
   if rocr_devices:
       print(f"Visible ROCR devices: {rocr_devices}")
   if cuda_devices:
       print(f"Visible CUDA devices: {cuda_devices}")

**Bash**:

.. code-block:: bash

   echo "HIP devices: $HIP_VISIBLE_DEVICES"
   echo "ROCR devices: $ROCR_VISIBLE_DEVICES"
   echo "CUDA devices: $CUDA_VISIBLE_DEVICES"

Environment Variable Behavior
------------------------------

Variable Not Set
~~~~~~~~~~~~~~~~

**Conditions**:

- No GPU resources allocated to job
- No AMD/ROCM-compatible GPU resources allocated
- User has already set any of the three visible-devices variables

**Effect**: No environment variables are modified

Empty Variable
~~~~~~~~~~~~~~

**Conditions**:

- GPU resources allocated but ``_amd_gpus`` returns an empty list
- All allocated GPUs filtered out by vendor compatibility

**Effect**: Environment variables are not set

Debugging Environment Variables
---------------------------------

.. code-block:: console

   # Run with verbose logging
   python3 -m canary run --gpu-backend=amd --verbose ./tests

   # Check job environment
   python3 -m canary run --gpu-backend=amd -p gpus=1 tests/env_check.py

   # Test specific GPU allocation with vendor constraint
   python3 -m canary run --gpu-backend=amd -p "gpus=2,vendor=AMD" tests/gpu_test.py

Environment Variable Limitations
----------------------------------

1. **User Override Priority**: If any of the three visible-devices variables is already set,
   none of them are configured automatically
2. **Vendor Compatibility**: Only sets variables for AMD/ROCM-compatible GPUs
3. **Local Device IDs**: Uses node-local IDs, not global IDs
4. **No Validation**: Does not validate device existence
5. **No Error Handling**: Silently skips if conditions not met
6. **Job-Specific**: Variables are set per-job, not globally
7. **Process-Specific**: Only affects the job process

Best Practices
--------------

1. **Use Vendor-Specific Variables**: Check ``HIP_VISIBLE_DEVICES`` for HIP applications and
   ``ROCR_VISIBLE_DEVICES`` for ROCr applications
2. **Respect User Overrides**: Don't override user-set visible-devices variables
3. **Check Variable Presence**: Verify variables are set before using them
4. **Handle Missing Variables**: Provide fallback behavior
5. **Test Environment**: Verify environment in test setup
6. **Consider Multi-Node**: Handle duplicate local IDs appropriately
