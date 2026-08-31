.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

NVIDIA GPU Extension
=====================

The ``canary_nvidia`` extension provides the NVIDIA implementation of Canary's shared GPU backend pattern. It follows the same fundamental approach as ``canary_amd`` but uses NVIDIA-specific tools (``nvidia-smi``) and environment variables (``CUDA_VISIBLE_DEVICES``).

Extension Type
--------------

**GPU backend discovery and runtime environment extension**

This extension implements Canary's shared GPU backend pattern with NVIDIA-specific details:

- **Detection**: Uses ``nvidia-smi`` to detect NVIDIA GPU availability (parallel to AMD's use of ``amd-smi``/``rocm-smi``)
- **Listing**: Enumerates NVIDIA GPU devices via ``nvidia-smi --query-gpu=index,uuid,name`` (parallel to AMD's ``amd-smi list --json``)
- **Environment**: Configures ``CUDA_VISIBLE_DEVICES`` for allocated GPUs (parallel to AMD's ``HIP_VISIBLE_DEVICES``/``ROCR_VISIBLE_DEVICES``)
- **Integration**: Plugs into the same Canary plugin hooks and resource pool framework as the AMD extension

The NVIDIA extension provides the NVIDIA-specific implementation of the shared GPU backend pattern, enabling consistent GPU support across different vendors.

Detection Mechanism
-------------------

**Tool**: ``nvidia-smi`` (NVIDIA System Management Interface)

**Detection Logic**:

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       return "nvidia" if shutil.which("nvidia-smi") else None

**Behavior**:

- Checks for ``nvidia-smi`` executable in system PATH
- Returns ``"nvidia"`` if tool is available
- Returns ``None`` if tool is not available
- Does not execute ``nvidia-smi`` during detection

GPU Enumeration
---------------

**Command**:

.. code-block:: console

   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits

**Output Format**:

.. code-block:: text

   0,GPU-12345678,Tesla V100
   1,GPU-87654321,Tesla V100
   2,GPU-11111111,GeForce RTX 3090

**Parsing Logic**:

.. code-block:: python

   def _nvidia_smi_list_gpus(config: canary.Config) -> list[dict] | None:
       if nvidia_smi := shutil.which("nvidia-smi"):
           args = [nvidia_smi, "--query-gpu=index,uuid,name", "--format=csv,noheader,nounits"]
           try:
               txt = subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True)
               gpu_specs = []
               for line in txt.splitlines():
                   id, uuid, name = [_.strip() for _ in line.split(",", 2)]
                   gpu_specs.append({"vendor": "nvidia", "id": id, "uuid": uuid, "slots": 1, "name": name})
               return gpu_specs
           except Exception:
               logger.debug(f"Failed to determine GPU counts from '{' '.join(args)}'")
       return None

**Returned Fields**:

- ``vendor``: Always ``"nvidia"``
- ``id``: Local device index (string)
- ``uuid``: Unique device identifier
- ``slots``: Always ``1``
- ``name``: Device name from nvidia-smi

Resource Specification
----------------------

NVIDIA GPU resources in Canary's resource pool:

.. code-block:: json

   {
     "id": "0",
     "slots": 1,
     "properties": {
       "vendor": "NVIDIA",
       "uuid": "GPU-12345678",
       "name": "Tesla V100"
     }
   }

Runtime Environment Configuration
---------------------------------

**Variable**: ``CUDA_VISIBLE_DEVICES``

**Configuration Logic**:

.. code-block:: python

   def canary_runteststart(case: canary.Job) -> None:
       # Respect user override
       if "CUDA_VISIBLE_DEVICES" in case.variables:
           return

       # Get NVIDIA-compatible GPUs
       gpus = _nvidia_gpus(case)
       if not gpus:
           return

       # Extract local IDs and deduplicate
       local_ids = [str(gpu["id"]) for gpu in gpus]
       visible = ",".join(dict.fromkeys(local_ids))

       # Set environment variable
       if visible:
           case.variables["CUDA_VISIBLE_DEVICES"] = visible

GPU Selection Logic
~~~~~~~~~~~~~~~~~~~

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

**Vendor Compatibility**:

- Accepts ``"NVIDIA"`` vendor property
- Accepts ``"UNKNOWN"`` vendor property (allows fallback to NVIDIA)
- Accepts empty vendor property (allows fallback to NVIDIA)
- Rejects other vendor values (e.g., ``"AMD"``, ``"ROCM"``)

Environment Variable Behavior
-----------------------------

**User Override**:

- If ``CUDA_VISIBLE_DEVICES`` already set in job variables, extension does not override
- User configuration takes precedence over automatic configuration

**Multi-Node Handling**:

- Deduplicates local GPU IDs while preserving order
- Important for multi-node allocations where nodes may have same local IDs
- Uses ``dict.fromkeys()`` to remove duplicates while preserving insertion order

**Empty Allocation**:

- If no NVIDIA-compatible GPUs allocated, no environment variable is set
- Job runs without CUDA_VISIBLE_DEVICES configuration

Failure Modes
-------------

**Detection Failure**:

- **Cause**: ``nvidia-smi`` not found in PATH
- **Effect**: Backend not available for selection
- **Solution**: Install NVIDIA drivers or use manual resource definition

**Enumeration Failure**:

- **Cause**: ``nvidia-smi`` execution fails or returns invalid output
- **Effect**: No GPU resources added to pool
- **Solution**: Check NVIDIA tool installation and permissions

**Runtime Configuration Failure**:

- **Cause**: No NVIDIA-compatible GPUs allocated to job
- **Effect**: ``CUDA_VISIBLE_DEVICES`` not set
- **Solution**: Ensure job requests NVIDIA-compatible GPU resources

Examples
--------

Basic Usage
~~~~~~~~~~~

.. code-block:: console

   # Auto-detect and use NVIDIA backend
   python3 -m canary run --gpu-backend=nvidia ./tests

Explicit GPU Request
~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Request 2 GPUs
   python3 -m canary run --gpu-backend=nvidia -p gpus=2 ./tests

Vendor-Specific Request
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Request NVIDIA GPUs explicitly
   python3 -m canary run --gpu-backend=nvidia -p "gpus=1,vendor=NVIDIA" ./tests

Resource Inspection
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Check discovered NVIDIA GPU resources
   python3 -m canary config show resource-pool --gpu-backend=nvidia

Manual Resource Definition
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   # When auto-discovery is unavailable
   resource_pool:
     nodes:
       - id: "local"
         resources:
           gpus:
             - id: "0"
               slots: 1
               properties:
                 vendor: "NVIDIA"
                 uuid: "GPU-12345678"
                 name: "Tesla V100"
             - id: "1"
               slots: 1
               properties:
                 vendor: "NVIDIA"
                 uuid: "GPU-87654321"
                 name: "Tesla V100"

Environment Variable Usage
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Job can read the configured environment
   import os

   cuda_devices = os.environ.get("CUDA_VISIBLE_DEVICES", "")
   if cuda_devices:
       print(f"Using CUDA devices: {cuda_devices}")
   else:
       print("No CUDA devices allocated")

Debugging
---------

Debugging NVIDIA GPU support:

.. code-block:: console

   # Check backend detection
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

   # Test nvidia-smi manually
   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits

   # Check tool availability
   which nvidia-smi

   # Test with explicit GPU request
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/gpu_test.py

Limitations
-----------

1. **Tool Dependency**: Requires ``nvidia-smi`` to be installed and available
2. **Local Node Only**: Only discovers GPUs on the local node
3. **Format Sensitivity**: Depends on specific ``nvidia-smi`` output format
4. **No Validation**: Does not validate GPU device existence or functionality
5. **User Override Priority**: User-set ``CUDA_VISIBLE_DEVICES`` always takes precedence
6. **Vendor Compatibility**: Only configures environment for NVIDIA-compatible GPUs
7. **No Error Recovery**: Silently skips if conditions not met

Best Practices
--------------

1. **Install NVIDIA Tools**: Ensure ``nvidia-smi`` is installed and in PATH
2. **Check Detection**: Verify backend detection with ``--verbose`` flag
3. **Test Environment**: Verify ``CUDA_VISIBLE_DEVICES`` in test setup
4. **Handle Missing Variables**: Provide fallback behavior when variable not set
5. **Respect User Overrides**: Don't override user-set environment variables
6. **Consider Multi-Node**: Handle duplicate local IDs appropriately
7. **Document Requirements**: Specify NVIDIA driver and tool requirements