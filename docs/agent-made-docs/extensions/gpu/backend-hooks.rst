.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

GPU Backend Hooks
==================

The ``canary_amd`` and ``canary_nvidia`` extensions implement identical plugin hooks that follow the same shared pattern for GPU backend integration. Both extensions provide parallel implementations of the same three hooks, differing only in vendor-specific tool usage and environment variable configuration.

Shared Hook Pattern
-------------------

Both GPU vendor extensions implement the same three plugin hooks with analogous behavior:

1. **``canary_gpu_backend_detect``**: Detect backend availability using vendor-specific tools
2. **``canary_gpu_list_gpus``**: List GPU devices using vendor-specific commands
3. **``canary_runteststart``**: Configure runtime environment with vendor-specific variables

This shared hook pattern enables consistent integration with Canary's GPU support framework while accommodating vendor-specific requirements.

Plugin Hook Specifications
--------------------------

canary_gpu_backend_detect
~~~~~~~~~~~~~~~~~~~~~~~~~

**Purpose**: Detect whether a GPU backend is available

**Signature**:

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       ...

**Called**: During Canary configuration phase

**Receives**: Canary configuration object

**Returns**:

- Backend identifier string ("nvidia" or "amd") if available
- None if backend is not available

**Effect**: Registers the backend as available for selection

**Failure Mode**: Returns None if vendor tools are missing or detection fails

NVIDIA Implementation
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       return "nvidia" if shutil.which("nvidia-smi") else None

**Behavior**:

- Checks for nvidia-smi executable in PATH
- Returns "nvidia" if found
- Returns None if not found

AMD Implementation
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       return "amd" if (shutil.which("amd-smi") or shutil.which("rocm-smi")) else None

**Behavior**:

- Checks for amd-smi or rocm-smi executables in PATH
- Returns "amd" if either tool is found
- Returns None if neither tool is found

canary_gpu_list_gpus
~~~~~~~~~~~~~~~~~~~~

**Purpose**: Enumerate available GPU devices

**Signature**:

.. code-block:: python

   def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
       ...

**Called**: During resource pool population

**Receives**: Canary configuration object

**Returns**:

- List of GPU specification dictionaries if GPUs found
- None if no GPUs found or enumeration fails

**Effect**: Populates resource pool with GPU resources

**Failure Mode**: Returns None if vendor tools fail or output is invalid

NVIDIA Implementation
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
       return _nvidia_smi_list_gpus(config)

**Behavior**:

- Uses nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits
- Parses CSV output to extract GPU information
- Returns list of GPU specs with vendor, id, uuid, and slots
- Returns None on any parsing error

AMD Implementation
~~~~~~~~~~~~~~~~~~

.. code-block:: python

   def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
       if gpu_specs := _amd_smi_list_gpus(config):
           return gpu_specs
       elif gpu_specs := _rocm_smi_list_gpus(config):
           return gpu_specs
       return None

**Behavior**:

- Tries amd-smi list --json first
- Falls back to rocm-smi output parsing if amd-smi fails
- Returns list of GPU specs with vendor, id, uuid, and slots
- Returns None if both methods fail

canary_runteststart
~~~~~~~~~~~~~~~~~~~

**Purpose**: Configure runtime environment for GPU jobs

**Signature**:

.. code-block:: python

   def canary_runteststart(case: canary.Job) -> None:
       ...

**Called**: Before each job execution

**Receives**: Job object with allocated resources

**Returns**: None

**Effect**: Sets vendor-specific environment variables

**Failure Mode**: Silently skips if conditions not met

NVIDIA Implementation
~~~~~~~~~~~~~~~~~~~~~

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

- Respects user-set CUDA_VISIBLE_DEVICES (doesn't override)
- Extracts NVIDIA-compatible GPUs from job resources
- Sets CUDA_VISIBLE_DEVICES to comma-separated local GPU IDs
- Deduplicates IDs while preserving order (important for multi-node)

AMD Implementation
~~~~~~~~~~~~~~~~~~

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

- Respects user-set visible device variables (doesn't override)
- Extracts AMD-compatible GPUs from job resources
- Sets HIP_VISIBLE_DEVICES, ROCR_VISIBLE_DEVICES, and CUDA_VISIBLE_DEVICES
- Deduplicates IDs while preserving order (important for multi-node)

Hook Interaction Flow
---------------------

The GPU hooks interact with Canary in this sequence:

1. **Configuration Phase**:
   - canary_gpu_backend_detect called for all registered GPU extensions
   - Available backends registered for selection
   - User selection (--gpu-backend) determines active backend

2. **Resource Pool Population**:
   - canary_gpu_list_gpus called for selected backend
   - Returned GPU specs added to resource pool
   - GPUs become available for job allocation

3. **Job Execution**:
   - Jobs request GPU resources through resource requirements
   - Canary allocates GPU resources to jobs
   - canary_runteststart called before job execution
   - Environment variables set based on allocated GPUs

GPU Resource Specification
---------------------------

GPU specifications returned by canary_gpu_list_gpus have this structure:

.. code-block:: python

   {
       "vendor": "nvidia",      # or "amd"
       "id": "0",              # Local device ID
       "uuid": "GPU-12345",    # Unique device identifier
       "slots": 1,             # Number of GPU slots
       "name": "..."           # Optional: Device name
   }

These specs are converted to Canary resource format:

.. code-block:: python

   {
       "id": "0",              # Node-local runtime device ID
       "slots": 1,             # Number of slots
       "properties": {
           "vendor": "NVIDIA",   # Vendor identifier
           "uuid": "GPU-12345",  # Unique identifier
           "name": "..."         # Optional: Device name
       }
   }

GPU Selection Logic
-------------------

The _nvidia_gpus and _amd_gpus functions implement vendor-specific GPU selection:

NVIDIA Selection
~~~~~~~~~~~~~~~~

.. code-block:: python

   def _nvidia_gpus(case: canary.Job) -> list[dict[str, Any]]:
       # Extract GPU resources from job
       gpus = case.resources.get("gpus", [])

       # Filter for NVIDIA-compatible GPUs
       nvidia_gpus = []
       for gpu in gpus:
           vendor = str(gpu.get("properties", {}).get("vendor", "")).upper()
           if vendor in {"NVIDIA", "UNKNOWN", ""}:
               nvidia_gpus.append(gpu)

       return nvidia_gpus

**Vendor Compatibility**: Accepts NVIDIA, UNKNOWN, or empty vendor values

AMD Selection
~~~~~~~~~~~~~

.. code-block:: python

   def _amd_gpus(case: canary.Job) -> list[dict[str, Any]]:
       # Extract GPU resources from job
       gpus = case.resources.get("gpus", [])

       # Filter for AMD-compatible GPUs
       amd_gpus = []
       for gpu in gpus:
           vendor = str(gpu.get("properties", {}).get("vendor", "")).upper()
           if vendor in {"AMD", "ROCM"}:
               amd_gpus.append(gpu)

       return amd_gpus

**Vendor Compatibility**: Only accepts AMD or ROCM vendor values

Key Differences
---------------

1. **Vendor Detection**:
   - NVIDIA: nvidia-smi only
   - AMD: amd-smi or rocm-smi

2. **Enumeration Commands**:
   - NVIDIA: nvidia-smi --query-gpu=...
   - AMD: amd-smi list --json or rocm-smi parsing

3. **Environment Variables**:
   - NVIDIA: CUDA_VISIBLE_DEVICES only
   - AMD: HIP_VISIBLE_DEVICES, ROCR_VISIBLE_DEVICES, CUDA_VISIBLE_DEVICES

4. **Vendor Compatibility**:
   - NVIDIA: Accepts UNKNOWN and empty vendor values
   - AMD: Only accepts AMD and ROCM vendor values

5. **User Override Variables**:
   - NVIDIA: CUDA_VISIBLE_DEVICES
   - AMD: HIP_VISIBLE_DEVICES, ROCR_VISIBLE_DEVICES, CUDA_VISIBLE_DEVICES

Hook Failure Modes
------------------

Backend Detection Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Missing Tools**: Returns None (backend not available)
- **Permission Issues**: Returns None (tool execution fails)
- **Invalid Output**: Returns None (parsing fails)

GPU Enumeration Failures
~~~~~~~~~~~~~~~~~~~~~~~~

- **Tool Execution Failure**: Returns None (subprocess fails)
- **Invalid Output Format**: Returns None (JSON/CSV parsing fails)
- **Unexpected Data**: Returns None (validation fails)

Runtime Configuration Failures
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **No GPU Resources**: Silently skips (no environment variables set)
- **User Override**: Silently skips (respects user settings)
- **Invalid Resource Format**: Returns empty list (no environment variables set)

Debugging Hook Behavior
-----------------------

To debug GPU hook behavior:

.. code-block:: console

   # Check which backends are detected
   python3 -m canary run --gpu-backend=auto --verbose ./tests

   # Force specific backend
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

   # Check resource pool with GPU backend
   python3 -m canary config show resource-pool --gpu-backend=auto

   # Test with explicit GPU requirements
   python3 -m canary run --gpu-backend=auto -p gpus=1 --verbose ./tests

Hook behavior is logged at DEBUG level when verbose mode is enabled.