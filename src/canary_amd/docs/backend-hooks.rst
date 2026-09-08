.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

AMD GPU Backend Hooks
======================

``canary_amd`` implements three plugin hooks that integrate with Canary's GPU backend framework.
For the equivalent NVIDIA implementation, see the ``canary_nvidia`` plugin.

Plugin Hook Specifications
--------------------------

canary_gpu_backend_detect
~~~~~~~~~~~~~~~~~~~~~~~~~

**Purpose**: Detect whether the AMD GPU backend is available

**Signature**:

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       ...

**Called**: During Canary configuration phase

**Receives**: Canary configuration object

**Returns**:

- ``"amd"`` if ``amd-smi`` or ``rocm-smi`` is found in PATH
- ``None`` if neither tool is found

**Effect**: Registers the AMD backend as available for selection

**Failure Mode**: Returns ``None`` if both tools are missing or detection fails

**Implementation**:

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       return "amd" if (shutil.which("amd-smi") or shutil.which("rocm-smi")) else None

canary_gpu_list_gpus
~~~~~~~~~~~~~~~~~~~~

**Purpose**: Enumerate available AMD GPU devices

**Signature**:

.. code-block:: python

   def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
       ...

**Called**: During resource pool population

**Receives**: Canary configuration object

**Returns**:

- List of GPU specification dictionaries if GPUs are found
- ``None`` if no GPUs are found or enumeration fails

**Effect**: Populates the resource pool with AMD GPU resources

**Failure Mode**: Returns ``None`` if both ``amd-smi`` and ``rocm-smi`` fail

**Implementation**:

.. code-block:: python

   def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
       if gpu_specs := _amd_smi_list_gpus(config):
           return gpu_specs
       elif gpu_specs := _rocm_smi_list_gpus(config):
           return gpu_specs
       return None

**Behavior**:

- Tries ``amd-smi list --json`` first
- Falls back to ``rocm-smi`` output parsing if ``amd-smi`` fails or is unavailable
- Returns list of GPU specs with ``vendor``, ``id``, ``uuid``, and ``slots``
- Returns ``None`` if both methods fail

canary_runteststart
~~~~~~~~~~~~~~~~~~~

**Purpose**: Configure runtime environment for AMD GPU jobs

**Signature**:

.. code-block:: python

   def canary_runteststart(case: canary.Job) -> None:
       ...

**Called**: Before each job execution

**Receives**: Job object with allocated resources

**Returns**: ``None``

**Effect**: Sets ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and ``CUDA_VISIBLE_DEVICES``

**Failure Mode**: Silently skips if conditions not met

**Implementation**:

.. code-block:: python

   def canary_runteststart(case: canary.Job) -> None:
       if any(var in case.variables for var in _AMD_VISIBLE_DEVICES_VARIABLES):
           return  # User override: don't override

       gpus = _amd_gpus(case)
       if not gpus:
           return  # No AMD GPUs allocated

       local_ids = [str(gpu["id"]) for gpu in gpus]
       visible = ",".join(dict.fromkeys(local_ids))

       if visible:
           case.variables["HIP_VISIBLE_DEVICES"] = visible
           case.variables["ROCR_VISIBLE_DEVICES"] = visible
           case.variables["CUDA_VISIBLE_DEVICES"] = visible

**Behavior**:

- Respects user-set visible-devices variables (does not override if any is already set)
- Extracts AMD-compatible GPUs from job resources
- Sets ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and ``CUDA_VISIBLE_DEVICES``
  to the same comma-separated local GPU IDs
- Deduplicates IDs while preserving order (important for multi-node)

Hook Interaction Flow
---------------------

The GPU hooks interact with Canary in this sequence:

1. **Configuration Phase**:
   - ``canary_gpu_backend_detect`` is called for all registered GPU extensions
   - Available backends are registered for selection
   - User selection (``--gpu-backend``) determines the active backend

2. **Resource Pool Population**:
   - ``canary_gpu_list_gpus`` is called for the selected backend
   - Returned GPU specs are added to the resource pool
   - GPUs become available for job allocation

3. **Job Execution**:
   - Jobs request GPU resources through resource requirements
   - Canary allocates GPU resources to jobs
   - ``canary_runteststart`` is called before job execution
   - ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and ``CUDA_VISIBLE_DEVICES``
     are set based on allocated GPUs

GPU Resource Specification
---------------------------

GPU specifications returned by ``canary_gpu_list_gpus`` have this structure:

.. code-block:: python

   {
       "vendor": "amd",        # Vendor identifier
       "id": "0",              # Local device ID
       "uuid": "GPU-12345",    # Unique device identifier (or index for rocm-smi)
       "slots": 1,             # Number of GPU slots
   }

These specs are converted to Canary resource format:

.. code-block:: python

   {
       "id": "0",              # Node-local runtime device ID
       "slots": 1,             # Number of slots
       "properties": {
           "vendor": "AMD",    # Vendor identifier (uppercased)
           "uuid": "GPU-12345" # Unique identifier
       }
   }

GPU Selection Logic
-------------------

The ``_amd_gpus`` function filters job resources for AMD-compatible GPUs:

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

**Vendor Compatibility**: Accepts only ``AMD`` or ``ROCM`` vendor values.
Rejects ``NVIDIA``, ``UNKNOWN``, empty string, and any other vendor values.

Hook Failure Modes
------------------

Backend Detection Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Missing Tools**: Returns ``None`` (backend not available)
- **Permission Issues**: Returns ``None`` (tool execution fails)

GPU Enumeration Failures
~~~~~~~~~~~~~~~~~~~~~~~~

- **amd-smi failure**: Falls through to ``rocm-smi``
- **rocm-smi failure**: Returns ``None`` (both methods failed)
- **Invalid JSON output** (amd-smi): Returns ``None``
- **No GPU pattern matches** (rocm-smi): Returns ``None``

Runtime Configuration Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **No GPU Resources**: Silently skips (no environment variables set)
- **User Override**: Silently skips (respects user settings)
- **Invalid Resource Format**: Returns empty list (no environment variables set)

Debugging Hook Behavior
-----------------------

.. code-block:: console

   # Check whether the AMD backend is detected
   python3 -m canary run --gpu-backend=amd --verbose ./tests

   # Check resource pool with AMD backend
   python3 -m canary config show resource-pool --gpu-backend=amd

   # Test with explicit GPU requirements
   python3 -m canary run --gpu-backend=amd -p gpus=1 --verbose ./tests

Hook behavior is logged at DEBUG level when verbose mode is enabled.
