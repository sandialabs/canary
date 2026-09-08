.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

AMD GPU Resource Discovery
===========================

``canary_amd`` discovers available AMD GPU devices using ``amd-smi`` or ``rocm-smi`` and populates
Canary's resource pool with the discovered devices. This enables jobs to request and use AMD GPU
resources.

Discovery Process
-----------------

AMD GPU discovery follows this process:

1. **Backend Selection**: User selects the AMD GPU backend via ``--gpu-backend=amd``
   (or ``auto`` if only AMD tools are found)
2. **Tool Detection**: Extension checks for ``amd-smi`` or ``rocm-smi`` in PATH
3. **Device Enumeration**: Extension lists available AMD GPU devices
4. **Resource Conversion**: Device information is converted to Canary resource format
5. **Pool Population**: GPU resources are added to Canary's resource pool

Backend Selection
~~~~~~~~~~~~~~~~~

GPU backend selection modes:

- **none** (default): No GPU backend
- **auto**: Automatically select available backend
- **amd**: Use AMD backend explicitly
- **nvidia**: Use NVIDIA backend explicitly (requires ``canary_nvidia``)

When ``auto`` mode detects multiple backends, explicit selection is required.

Detection
---------

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       return "amd" if (shutil.which("amd-smi") or shutil.which("rocm-smi")) else None

**Behavior**:

- Checks for ``amd-smi`` or ``rocm-smi`` executables in system PATH
- Returns ``"amd"`` if either tool is found
- Returns ``None`` if neither tool is found

Enumeration
-----------

**Primary Method**: ``amd-smi list --json``

.. code-block:: console

   amd-smi list --json

**Output Format**:

.. code-block:: json

   [
     {"gpu": "0", "uuid": "GPU-12345678"},
     {"gpu": "1", "uuid": "GPU-87654321"}
   ]

**Parsing**:

- Parses JSON output
- Extracts ``gpu`` index and ``uuid`` fields
- Normalizes UUID format (prepends ``"GPU-"`` if missing)
- Creates a GPU specification for each device

**Fallback Method**: ``rocm-smi`` output parsing

.. code-block:: console

   rocm-smi

**Output Parsing**:

- Searches for patterns like ``GPU[0]`` using regex ``\bGPU\[(\d+)\]\b``
- Extracts GPU indices from output
- Deduplicates indices while preserving order
- Uses index as both ID and UUID (no stable UUID available from ``rocm-smi``)
- Creates a GPU specification for each found index

Resource Specification
----------------------

.. code-block:: python

   {
       "vendor": "amd",
       "id": "0",
       "uuid": "GPU-12345678",
       "slots": 1
   }

**Fields**:

- ``vendor``: Always ``"amd"``
- ``id``: Local device index (string)
- ``uuid``: Unique device identifier (or index for ``rocm-smi`` fallback)
- ``slots``: Number of GPU slots (always ``1``)

Resource Pool Integration
-------------------------

Discovered GPU resources are converted to Canary's resource format:

.. code-block:: python

   {
       "id": "0",                  # Node-local runtime device ID
       "slots": 1,                 # Number of GPU slots
       "properties": {
           "vendor": "AMD",        # Vendor identifier (uppercased)
           "uuid": "GPU-12345678", # Unique device identifier
       }
   }

**Conversion Process**:

1. GPU specs are returned by ``canary_gpu_list_gpus``
2. Vendor string is converted to uppercase
3. UUID property is preserved
4. Resource ID is set to the local device ID
5. Slots is set to the specified value (always ``1``)
6. Resources are added to the first node's GPU pool

Resource Pool Population
------------------------

GPU resources are added to Canary's resource pool during configuration via Canary's core
``canary_fill_gpu`` hook:

- Only populates the first (local) node
- Skips if GPUs are already present
- Skips if no backend is selected
- Adds all discovered GPUs to the resource pool

Manual Resource Definition
--------------------------

When auto-discovery is unavailable or insufficient, GPUs can be manually defined:

.. code-block:: yaml

   resource_pool:
     allow_multinode: true
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

**Use Cases**:

- Containerized environments without ``amd-smi``/``rocm-smi``
- Custom GPU configurations
- Testing without actual hardware
- Overriding auto-discovery results

Discovery Failure Modes
-----------------------

Tool Missing
~~~~~~~~~~~~

**Symptoms**: No GPU backend detected

**Causes**:

- Neither ``amd-smi`` nor ``rocm-smi`` is installed
- Tools not in system PATH
- Permission issues preventing tool execution

**Solutions**:

- Install AMD ROCm stack (which includes ``amd-smi`` and/or ``rocm-smi``)
- Ensure tools are in PATH
- Check permissions
- Use manual resource definition

Tool Execution Failure
~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: Backend detected but no GPUs discovered

**Causes**:

- Tool execution permissions
- Invalid tool output format
- Tool configuration issues
- Hardware not available

**Solutions**:

- Check tool execution permissions
- Verify ``amd-smi``/``rocm-smi`` installation
- Test tools manually
- Use manual resource definition

Invalid Output Format
~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: No GPUs discovered despite tools being available

**Causes**:

- Unexpected tool output format
- Tool version incompatibility
- JSON parsing errors (``amd-smi``)
- No ``GPU[N]`` pattern matches (``rocm-smi``)

**Solutions**:

- Check tool version compatibility
- Test tool output manually: ``amd-smi list --json`` or ``rocm-smi``
- Use manual resource definition

Debugging Discovery
-------------------

.. code-block:: console

   # Test backend detection
   python3 -m canary run --gpu-backend=amd --verbose ./tests

   # Check resource pool
   python3 -m canary config show resource-pool --gpu-backend=amd

   # Test amd-smi manually
   amd-smi list --json

   # Test rocm-smi manually (fallback)
   rocm-smi

   # Check tool availability
   which amd-smi
   which rocm-smi

Discovery Examples
------------------

Basic Discovery
~~~~~~~~~~~~~~~

.. code-block:: console

   # Auto-detect and use AMD backend
   python3 -m canary run --gpu-backend=auto ./tests

Explicit Backend
~~~~~~~~~~~~~~~~

.. code-block:: console

   # Use AMD backend explicitly
   python3 -m canary run --gpu-backend=amd ./tests

Resource Inspection
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Check discovered AMD GPU resources
   python3 -m canary config show resource-pool --gpu-backend=amd

Manual Override
~~~~~~~~~~~~~~~

.. code-block:: console

   # Use manual resource definition when auto-discovery fails
   python3 -m canary run --resource-pool=custom_pool.yaml ./tests

Discovery Limitations
---------------------

1. **Local Node Only**: Auto-discovery only works for the local node
2. **Tool Dependence**: Requires ``amd-smi`` or ``rocm-smi`` to be installed
3. **Format Sensitivity**: Parsing depends on specific tool output formats
4. **UUID Stability**: ``rocm-smi`` fallback does not provide stable UUIDs
5. **Permission Requirements**: Tools may require specific permissions
6. **Container Limitations**: May not work in containerized environments without GPU passthrough
7. **Multi-Node**: Does not discover GPUs on remote nodes
