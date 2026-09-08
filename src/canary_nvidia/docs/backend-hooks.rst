.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

NVIDIA GPU Backend Hooks
=========================

``canary_nvidia`` implements three plugin hooks that integrate with Canary's GPU backend framework.
For the equivalent AMD implementation, see the ``canary_amd`` plugin.

Plugin Hook Specifications
--------------------------

canary_gpu_backend_detect
~~~~~~~~~~~~~~~~~~~~~~~~~

**Purpose**: Detect whether the NVIDIA GPU backend is available

**Signature**:

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       ...

**Called**: During Canary configuration phase

**Receives**: Canary configuration object

**Returns**:

- ``"nvidia"`` if ``nvidia-smi`` is found in PATH
- ``None`` if ``nvidia-smi`` is not found

**Effect**: Registers the NVIDIA backend as available for selection

**Failure Mode**: Returns ``None`` if ``nvidia-smi`` is missing or detection fails

**Implementation**:

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       return "nvidia" if shutil.which("nvidia-smi") else None

canary_gpu_list_gpus
~~~~~~~~~~~~~~~~~~~~

**Purpose**: Enumerate available NVIDIA GPU devices

**Signature**:

.. code-block:: python

   def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
       ...

**Called**: During resource pool population

**Receives**: Canary configuration object

**Returns**:

- List of GPU specification dictionaries if GPUs are found
- ``None`` if no GPUs are found or enumeration fails

**Effect**: Populates the resource pool with NVIDIA GPU resources

**Failure Mode**: Returns ``None`` if ``nvidia-smi`` fails or output is invalid

**Implementation**:

.. code-block:: python

   def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
       return _nvidia_smi_list_gpus(config)

**Behavior**:

- Uses ``nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits``
- Parses CSV output to extract GPU information
- Returns list of GPU specs with ``vendor``, ``id``, ``uuid``, and ``slots``
- Returns ``None`` on any parsing or execution error

canary_runteststart
~~~~~~~~~~~~~~~~~~~

**Purpose**: Configure runtime environment for NVIDIA GPU jobs

**Signature**:

.. code-block:: python

   def canary_runteststart(case: canary.Job) -> None:
       ...

**Called**: Before each job execution

**Receives**: Job object with allocated resources

**Returns**: ``None``

**Effect**: Sets ``CUDA_VISIBLE_DEVICES``

**Failure Mode**: Silently skips if conditions not met

**Implementation**:

.. code-block:: python

   def canary_runteststart(case: canary.Job) -> None:
       if "CUDA_VISIBLE_DEVICES" in case.variables:
           return  # User override: don't override

       gpus = _nvidia_gpus(case)
       if not gpus:
           return  # No NVIDIA GPUs allocated

       local_ids = [str(gpu["id"]) for gpu in gpus]
       visible = ",".join(dict.fromkeys(local_ids))

       if visible:
           case.variables["CUDA_VISIBLE_DEVICES"] = visible

**Behavior**:

- Respects user-set ``CUDA_VISIBLE_DEVICES`` (does not override)
- Extracts NVIDIA-compatible GPUs from job resources
- Sets ``CUDA_VISIBLE_DEVICES`` to comma-separated local GPU IDs
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
   - ``CUDA_VISIBLE_DEVICES`` is set based on allocated GPUs

GPU Resource Specification
---------------------------

GPU specifications returned by ``canary_gpu_list_gpus`` have this structure:

.. code-block:: python

   {
       "vendor": "nvidia",     # Vendor identifier
       "id": "0",              # Local device ID
       "uuid": "GPU-12345",    # Unique device identifier
       "slots": 1,             # Number of GPU slots
   }

These specs are converted to Canary resource format:

.. code-block:: python

   {
       "id": "0",              # Node-local runtime device ID
       "slots": 1,             # Number of slots
       "properties": {
           "vendor": "NVIDIA",   # Vendor identifier (uppercased)
           "uuid": "GPU-12345",  # Unique identifier
       }
   }

GPU Selection Logic
-------------------

The ``_nvidia_gpus`` function filters job resources for NVIDIA-compatible GPUs:

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

Hook Failure Modes
------------------

Backend Detection Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Missing Tool**: Returns ``None`` (backend not available)
- **Permission Issues**: Returns ``None`` (tool execution fails)

GPU Enumeration Failures
~~~~~~~~~~~~~~~~~~~~~~~~

- **Tool Execution Failure**: Returns ``None`` (subprocess fails)
- **Invalid Output Format**: Returns ``None`` (CSV parsing fails)
- **Unexpected Data**: Returns ``None`` (validation fails)

Runtime Configuration Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **No GPU Resources**: Silently skips (no environment variables set)
- **User Override**: Silently skips (respects user settings)
- **Invalid Resource Format**: Returns empty list (no environment variables set)

Debugging Hook Behavior
-----------------------

.. code-block:: console

   # Check whether the NVIDIA backend is detected
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

   # Check resource pool with NVIDIA backend
   python3 -m canary config show resource-pool --gpu-backend=nvidia

   # Test with explicit GPU requirements
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 --verbose ./tests

Hook behavior is logged at DEBUG level when verbose mode is enabled.
