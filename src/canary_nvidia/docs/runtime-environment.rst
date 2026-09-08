.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

NVIDIA Runtime Environment
===========================

``canary_nvidia`` configures runtime environment variables for jobs that have been allocated NVIDIA
GPU resources. This enables jobs to access the specific GPU devices assigned to them.

Environment Variable Configuration
-----------------------------------

The extension sets ``CUDA_VISIBLE_DEVICES`` through the ``canary_runteststart`` hook, which is
called before each job execution.

Configuration Process
---------------------

1. **Job Resource Allocation**: Canary allocates GPU resources to the job
2. **Hook Invocation**: ``canary_runteststart`` is called before job execution
3. **GPU Selection**: Extension filters allocated GPUs by NVIDIA vendor compatibility
4. **Environment Setup**: Extension sets ``CUDA_VISIBLE_DEVICES``
5. **Job Execution**: Job runs with the configured environment

NVIDIA Environment Configuration
---------------------------------

**Variable**: ``CUDA_VISIBLE_DEVICES``

**Purpose**: Controls which GPU devices are visible to CUDA applications

**Format**: Comma-separated list of local GPU device IDs

**Example**:

.. code-block:: text

   CUDA_VISIBLE_DEVICES=0,1,2

**Behavior**:

- Sets ``CUDA_VISIBLE_DEVICES`` to the allocated GPU local IDs
- Deduplicates IDs while preserving order
- Only sets the variable if the user has not already set it
- Only sets the variable if NVIDIA-compatible GPUs are allocated

**Selection Logic**:

.. code-block:: python

   def _nvidia_gpus(case: canary.Job) -> list[dict[str, Any]]:
       resources = getattr(case, "resources", None)
       if not isinstance(resources, dict):
           return []

       gpus = resources.get("gpus", [])
       if not isinstance(gpus, list):
           return []

       nvidia_gpus = []
       for gpu in gpus:
           if not isinstance(gpu, dict):
               return []

           properties = gpu.get("properties", {})
           if not isinstance(properties, dict):
               return []

           vendor = str(properties.get("vendor", "")).upper()
           if vendor not in {"NVIDIA", "UNKNOWN", ""}:
               return []

           if "id" not in gpu:
               return []

           nvidia_gpus.append(gpu)

       return nvidia_gpus

**Vendor Compatibility**: Accepts ``NVIDIA``, ``UNKNOWN``, or empty vendor values.
Rejects ``AMD``, ``ROCM``, and any other vendor values.

User Override Behavior
----------------------

The extension respects user-set environment variables:

.. code-block:: python

   if "CUDA_VISIBLE_DEVICES" in case.variables:
       return  # User override: don't override

**Effect**:

- User-set ``CUDA_VISIBLE_DEVICES`` takes precedence
- The extension does not override user configurations
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

   CUDA_VISIBLE_DEVICES=0

Multiple GPUs
~~~~~~~~~~~~~

**Allocation**: 3 GPUs with local IDs 0, 1, 2

.. code-block:: text

   CUDA_VISIBLE_DEVICES=0,1,2

Multi-Node with Duplicate IDs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Allocation**: GPU 0 from node A, GPU 0 from node B, GPU 1 from node A

**Result**:

.. code-block:: text

   CUDA_VISIBLE_DEVICES=0,1  # Deduplicated, order preserved

Reading Environment Variables
------------------------------

Jobs can read the configured environment variable:

**Python**:

.. code-block:: python

   import os

   cuda_devices = os.environ.get("CUDA_VISIBLE_DEVICES", "")
   if cuda_devices:
       print(f"Visible CUDA devices: {cuda_devices}")
   else:
       print("No CUDA devices allocated")

**Bash**:

.. code-block:: bash

   echo "CUDA devices: $CUDA_VISIBLE_DEVICES"

Environment Variable Behavior
------------------------------

Variable Not Set
~~~~~~~~~~~~~~~~

**Conditions**:

- No GPU resources allocated to job
- No NVIDIA-compatible GPU resources allocated
- User has already set ``CUDA_VISIBLE_DEVICES``

**Effect**: Environment variable is not modified

Empty Variable
~~~~~~~~~~~~~~

**Conditions**:

- GPU resources allocated but ``_nvidia_gpus`` returns an empty list
- All allocated GPUs filtered out by vendor compatibility

**Effect**: Environment variable is not set

Debugging Environment Variables
---------------------------------

.. code-block:: console

   # Run with verbose logging
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

   # Check job environment
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/env_check.py

Environment Variable Limitations
----------------------------------

1. **User Override Priority**: User-set ``CUDA_VISIBLE_DEVICES`` always takes precedence
2. **Vendor Compatibility**: Only sets the variable for NVIDIA-compatible GPUs
3. **Local Device IDs**: Uses node-local IDs, not global IDs
4. **No Validation**: Does not validate device existence
5. **No Error Handling**: Silently skips if conditions not met
6. **Job-Specific**: Variable is set per-job, not globally
7. **Process-Specific**: Only affects the job process

Best Practices
--------------

1. **Respect User Overrides**: Don't override user-set ``CUDA_VISIBLE_DEVICES``
2. **Check Variable Presence**: Verify the variable is set before using it
3. **Handle Missing Variables**: Provide fallback behavior
4. **Test Environment**: Verify environment in test setup
5. **Consider Multi-Node**: Handle duplicate local IDs appropriately
