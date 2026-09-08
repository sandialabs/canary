.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

NVIDIA GPU Resource Discovery
==============================

``canary_nvidia`` discovers available NVIDIA GPU devices using ``nvidia-smi`` and populates
Canary's resource pool with the discovered devices. This enables jobs to request and use NVIDIA
GPU resources.

Discovery Process
-----------------

NVIDIA GPU discovery follows this process:

1. **Backend Selection**: User selects the NVIDIA GPU backend via ``--gpu-backend=nvidia``
   (or ``auto`` if only NVIDIA tools are found)
2. **Tool Detection**: Extension checks for ``nvidia-smi`` in PATH
3. **Device Enumeration**: Extension lists available NVIDIA GPU devices
4. **Resource Conversion**: Device information is converted to Canary resource format
5. **Pool Population**: GPU resources are added to Canary's resource pool

Backend Selection
~~~~~~~~~~~~~~~~~

GPU backend selection modes:

- **none** (default): No GPU backend
- **auto**: Automatically select available backend
- **nvidia**: Use NVIDIA backend explicitly
- **amd**: Use AMD backend explicitly (requires ``canary_amd``)

When ``auto`` mode detects multiple backends, explicit selection is required.

Detection
---------

.. code-block:: python

   def canary_gpu_backend_detect(config: canary.Config) -> str | None:
       return "nvidia" if shutil.which("nvidia-smi") else None

**Behavior**:

- Checks for ``nvidia-smi`` executable in system PATH
- Returns ``"nvidia"`` if the tool is found
- Returns ``None`` if the tool is not found

Enumeration
-----------

**Command**:

.. code-block:: console

   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits

**Output Format**:

.. code-block:: text

   0,GPU-12345678,Tesla V100
   1,GPU-87654321,Tesla V100
   2,GPU-11111111,GeForce RTX 3090

**Parsing**:

- Splits CSV output by lines
- Splits each line by commas (max 2 splits to preserve name field)
- Extracts index and UUID fields; name field is captured but stored separately
- Creates a GPU specification for each device

Resource Specification
----------------------

.. code-block:: python

   {
       "vendor": "nvidia",
       "id": "0",
       "uuid": "GPU-12345678",
       "slots": 1
   }

**Fields**:

- ``vendor``: Always ``"nvidia"``
- ``id``: Local device index (string)
- ``uuid``: Unique device identifier from ``nvidia-smi``
- ``slots``: Number of GPU slots (always ``1``)

Resource Pool Integration
-------------------------

Discovered GPU resources are converted to Canary's resource format:

.. code-block:: python

   {
       "id": "0",                    # Node-local runtime device ID
       "slots": 1,                   # Number of GPU slots
       "properties": {
           "vendor": "NVIDIA",       # Vendor identifier (uppercased)
           "uuid": "GPU-12345678",   # Unique device identifier
       }
   }

**Conversion Process**:

1. GPU specs are returned by ``canary_gpu_list_gpus``
2. Vendor string is converted to uppercase
3. Additional properties (uuid) are preserved
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
                 vendor: "NVIDIA"
                 uuid: "GPU-12345678"
                 name: "Tesla V100"
             - id: "1"
               slots: 1
               properties:
                 vendor: "NVIDIA"
                 uuid: "GPU-87654321"
                 name: "Tesla V100"

**Use Cases**:

- Containerized environments without ``nvidia-smi``
- Custom GPU configurations
- Testing without actual hardware
- Overriding auto-discovery results

Discovery Failure Modes
-----------------------

Tool Missing
~~~~~~~~~~~~

**Symptoms**: No GPU backend detected

**Causes**:

- ``nvidia-smi`` not installed
- Tool not in system PATH
- Permission issues preventing tool execution

**Solutions**:

- Install NVIDIA drivers and tools
- Ensure ``nvidia-smi`` is in PATH
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
- Verify ``nvidia-smi`` installation
- Test tool manually
- Use manual resource definition

Invalid Output Format
~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: No GPUs discovered despite ``nvidia-smi`` being available

**Causes**:

- Unexpected tool output format
- Tool version incompatibility
- Parsing errors

**Solutions**:

- Check tool version compatibility
- Test tool output manually: ``nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits``
- Use manual resource definition

Debugging Discovery
-------------------

.. code-block:: console

   # Test backend detection
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

   # Check resource pool
   python3 -m canary config show resource-pool --gpu-backend=nvidia

   # Test nvidia-smi manually
   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits

   # Check tool availability
   which nvidia-smi

Discovery Examples
------------------

Basic Discovery
~~~~~~~~~~~~~~~

.. code-block:: console

   # Auto-detect and use NVIDIA backend
   python3 -m canary run --gpu-backend=auto ./tests

Explicit Backend
~~~~~~~~~~~~~~~~

.. code-block:: console

   # Use NVIDIA backend explicitly
   python3 -m canary run --gpu-backend=nvidia ./tests

Resource Inspection
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Check discovered NVIDIA GPU resources
   python3 -m canary config show resource-pool --gpu-backend=nvidia

Manual Override
~~~~~~~~~~~~~~~

.. code-block:: console

   # Use manual resource definition when auto-discovery fails
   python3 -m canary run --resource-pool=custom_pool.yaml ./tests

Discovery Limitations
---------------------

1. **Local Node Only**: Auto-discovery only works for the local node
2. **Tool Dependence**: Requires ``nvidia-smi`` to be installed
3. **Format Sensitivity**: Parsing depends on specific ``nvidia-smi`` output format
4. **Permission Requirements**: Tool may require specific permissions
5. **Container Limitations**: May not work in containerized environments without GPU passthrough
6. **Multi-Node**: Does not discover GPUs on remote nodes
