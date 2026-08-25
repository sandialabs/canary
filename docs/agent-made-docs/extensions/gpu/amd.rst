.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

AMD GPU Extension
=================

The ``canary_amd`` extension provides the AMD implementation of Canary's shared GPU backend pattern. It follows the same fundamental approach as ``canary_nvidia`` but uses AMD-specific tools (``amd-smi``/``rocm-smi``) and environment variables (``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, ``CUDA_VISIBLE_DEVICES``).

Extension Type
--------------

**GPU backend discovery and runtime environment extension**

This extension implements Canary's shared GPU backend pattern with AMD-specific details:

- **Detection**: Uses ``amd-smi`` or ``rocm-smi`` to detect AMD GPU availability (parallel to NVIDIA's use of ``nvidia-smi``)
- **Listing**: Enumerates AMD GPU devices via ``amd-smi list --json`` or ``rocm-smi`` parsing (parallel to NVIDIA's ``nvidia-smi --query-gpu``)
- **Environment**: Configures ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and ``CUDA_VISIBLE_DEVICES`` for allocated GPUs (parallel to NVIDIA's ``CUDA_VISIBLE_DEVICES``)
- **Integration**: Plugs into the same Canary plugin hooks and resource pool framework as the NVIDIA extension

The AMD extension provides the AMD-specific implementation of the shared GPU backend pattern, enabling consistent GPU support across different vendors.

Detection Mechanism
-------------------

**Tools**: ``amd-smi`` (AMD System Management Interface) or ``rocm-smi`` (ROCm System Management Interface)

**Detection Logic**:

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       return "amd" if (shutil.which("amd-smi") or shutil.which("rocm-smi")) else None

**Behavior**:

- Checks for ``amd-smi`` or ``rocm-smi`` executables in system PATH
- Returns ``"amd"`` if either tool is available
- Returns ``None`` if neither tool is available
- Does not execute tools during detection

GPU Enumeration
---------------

**Primary Method**: ``amd-smi list --json``

**Command**:

.. code-block:: console

   amd-smi list --json

**Output Format**:

.. code-block:: json

   [
     {"gpu": "0", "uuid": "GPU-12345678"},
     {"gpu": "1", "uuid": "GPU-87654321"}
   ]

**Parsing Logic**:

.. code-block:: python

   def _amd_smi_list_gpus(config: canary.Config) -> list[dict] | None:
       if amd_smi := shutil.which("amd-smi"):
           args = [amd_smi, "list", "--json"]
           try:
               txt = subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True)
               data = json.loads(txt)
               gpu_specs = []
               for entry in data:
                   id = entry["gpu"]
                   uuid = entry["uuid"]
                   if not uuid.startswith("GPU-"):
                       uuid = f"GPU-{uuid}"
                   gpu_specs.append({"vendor": "amd", "id": id, "uuid": uuid, "slots": 1})
               return gpu_specs
           except Exception:
               logger.debug(f"Failed to determine GPU counts from '{' '.join(args)}'")
       return None

**Fallback Method**: ``rocm-smi`` output parsing

**Command**:

.. code-block:: console

   rocm-smi

**Parsing Logic**:

.. code-block:: python

   def _rocm_smi_list_gpus(config: canary.Config) -> list[dict] | None:
       if rocm_smi := shutil.which("rocm-smi"):
           rx = re.compile(r"\bGPU\[(\d+)\]\b")
           args = [rocm-smi]
           try:
               txt = subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True)
               idxs = []
               for line in txt.splitlines():
                   if m := rx.search(line):
                       idxs.append(m.group(1))
               idxs = dedup(idxs)
               if idxs:
                   gpu_specs = [{"vendor": "amd", "id": i, "uuid": i, "slots": 1} for i in idxs]
                   return gpu_specs
           except Exception:
               logger.debug(f"Failed to determine GPU counts from '{' '.join(args)}'")
       return None

**Returned Fields**:

- ``vendor``: Always ``"amd"``
- ``id``: Local device index (string)
- ``uuid``: Unique device identifier (or index for rocm-smi fallback)
- ``slots``: Always ``1``

**Fallback Behavior**:

- Tries ``amd-smi`` first
- Falls back to ``rocm-smi`` if ``amd-smi`` fails or is unavailable
- Uses device index as UUID for ``rocm-smi`` (no stable UUID available)

Resource Specification
----------------------

AMD GPU resources in Canary's resource pool:

.. code-block:: json

   {
     "id": "0",
     "slots": 1,
     "properties": {
       "vendor": "AMD",
       "uuid": "GPU-12345678"
     }
   }

Runtime Environment Configuration
---------------------------------

**Variables**:

- ``HIP_VISIBLE_DEVICES``
- ``ROCR_VISIBLE_DEVICES``
- ``CUDA_VISIBLE_DEVICES``

**Configuration Logic**:

.. code-block:: python

   def canary_runteststart(case: canary.Job) -> None:
       # Respect user override
       if any(var in case.variables for var in _AMD_VISIBLE_DEVICES_VARIABLES):
           return

       # Get AMD-compatible GPUs
       gpus = _amd_gpus(case)
       if not gpus:
           return

       # Extract local IDs and deduplicate
       local_ids = [str(gpu["id"]) for gpu in gpus]
       visible = ",".join(dict.fromkeys(local_ids))

       # Set environment variables
       if visible:
           case.variables["HIP_VISIBLE_DEVICES"] = visible
           case.variables["ROCR_VISIBLE_DEVICES"] = visible
           case.variables["CUDA_VISIBLE_DEVICES"] = visible

**Visible Device Variables**:

.. code-block:: python

   _AMD_VISIBLE_DEVICES_VARIABLES = (
       "HIP_VISIBLE_DEVICES",
       "ROCR_VISIBLE_DEVICES",
       "CUDA_VISIBLE_DEVICES",
   )

GPU Selection Logic
~~~~~~~~~~~~~~~~~~~

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

           # Unlike NVIDIA, do not claim UNKNOWN devices
           # UNKNOWN resources fall through to CUDA handling
           if vendor not in {"AMD", "ROCM"}:
               return []

           amd_gpus.append(gpu)

       return amd_gpus

**Vendor Compatibility**:

- Accepts ``"AMD"`` vendor property
- Accepts ``"ROCM"`` vendor property
- Rejects ``"UNKNOWN"`` vendor property (allows fallback to NVIDIA)
- Rejects other vendor values (e.g., ``"NVIDIA"``, empty string)

Environment Variable Behavior
-----------------------------

**User Override**:

- If any of ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, or ``CUDA_VISIBLE_DEVICES`` already set in job variables, extension does not override
- User configuration takes precedence over automatic configuration

**Multi-Node Handling**:

- Deduplicates local GPU IDs while preserving order
- Important for multi-node allocations where nodes may have same local IDs
- Uses ``dict.fromkeys()`` to remove duplicates while preserving insertion order

**Empty Allocation**:

- If no AMD-compatible GPUs allocated, no environment variables are set
- Job runs without AMD-specific environment configuration

Failure Modes
-------------

**Detection Failure**:

- **Cause**: Neither ``amd-smi`` nor ``rocm-smi`` found in PATH
- **Effect**: Backend not available for selection
- **Solution**: Install AMD tools or use manual resource definition

**Enumeration Failure**:

- **Cause**: Both ``amd-smi`` and ``rocm-smi`` execution fails
- **Effect**: No GPU resources added to pool
- **Solution**: Check AMD tool installation and permissions

**Runtime Configuration Failure**:

- **Cause**: No AMD-compatible GPUs allocated to job
- **Effect**: AMD environment variables not set
- **Solution**: Ensure job requests AMD-compatible GPU resources

Examples
--------

Basic Usage
~~~~~~~~~~~

.. code-block:: console

   # Auto-detect and use AMD backend
   python3 -m canary run --gpu-backend=amd ./tests

Explicit GPU Request
~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Request 2 GPUs
   python3 -m canary run --gpu-backend=amd -p gpus=2 ./tests

Vendor-Specific Request
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Request AMD GPUs explicitly
   python3 -m canary run --gpu-backend=amd -p "gpus=1,vendor=AMD" ./tests

Resource Inspection
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Check discovered AMD GPU resources
   python3 -m canary config show resource-pool --gpu-backend=amd

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
                 vendor: "AMD"
                 uuid: "GPU-12345678"
             - id: "1"
               slots: 1
               properties:
                 vendor: "AMD"
                 uuid: "GPU-87654321"

Environment Variable Usage
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Job can read the configured environment
   import os

   hip_devices = os.environ.get("HIP_VISIBLE_DEVICES", "")
   rocr_devices = os.environ.get("ROCR_VISIBLE_DEVICES", "")
   cuda_devices = os.environ.get("CUDA_VISIBLE_DEVICES", "")

   if hip_devices:
       print(f"Using HIP devices: {hip_devices}")
   if rocr_devices:
       print(f"Using ROCR devices: {rocr_devices}")
   if cuda_devices:
       print(f"Using CUDA devices: {cuda_devices}")

Debugging
---------

Debugging AMD GPU support:

.. code-block:: console

   # Check backend detection
   python3 -m canary run --gpu-backend=amd --verbose ./tests

   # Test amd-smi manually
   amd-smi list --json

   # Test rocm-smi manually
   rocm-smi

   # Check tool availability
   which amd-smi
   which rocm-smi

   # Test with explicit GPU request
   python3 -m canary run --gpu-backend=amd -p gpus=1 tests/gpu_test.py

Limitations
-----------

1. **Tool Dependency**: Requires ``amd-smi`` or ``rocm-smi`` to be installed
2. **Local Node Only**: Only discovers GPUs on the local node
3. **Format Sensitivity**: Depends on specific tool output formats
4. **No Validation**: Does not validate GPU device existence or functionality
5. **User Override Priority**: User-set environment variables always take precedence
6. **Vendor Compatibility**: Only configures environment for AMD/ROCM-compatible GPUs
7. **No Error Recovery**: Silently skips if conditions not met
8. **Fallback Limitations**: ``rocm-smi`` parsing may not provide stable UUIDs
9. **Vendor Specificity**: Does not claim UNKNOWN devices (allows NVIDIA fallback)

Best Practices
--------------

1. **Install AMD Tools**: Ensure ``amd-smi`` or ``rocm-smi`` is installed and in PATH
2. **Check Detection**: Verify backend detection with ``--verbose`` flag
3. **Test Environment**: Verify AMD environment variables in test setup
4. **Handle Missing Variables**: Provide fallback behavior when variables not set
5. **Respect User Overrides**: Don't override user-set environment variables
6. **Consider Multi-Node**: Handle duplicate local IDs appropriately
7. **Document Requirements**: Specify AMD driver and tool requirements
8. **Prefer amd-smi**: Use ``amd-smi`` for more reliable UUID information