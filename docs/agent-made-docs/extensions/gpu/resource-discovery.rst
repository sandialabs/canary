.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

GPU Resource Discovery
=======================

The GPU vendor extensions discover available GPU devices using vendor-specific tools and populate Canary's resource pool with the discovered devices. This enables jobs to request and use GPU resources.

Discovery Process
-----------------

GPU discovery follows this process:

1. **Backend Selection**: User selects GPU backend via --gpu-backend option
2. **Tool Detection**: Extension checks for vendor-specific CLI tools
3. **Device Enumeration**: Extension lists available GPU devices
4. **Resource Conversion**: Device information converted to Canary resource format
5. **Pool Population**: GPU resources added to Canary's resource pool

Backend Selection
~~~~~~~~~~~~~~~~~

GPU backend selection modes:

- **none** (default): No GPU backend
- **auto**: Automatically select available backend
- **nvidia**: Use NVIDIA backend explicitly
- **amd**: Use AMD backend explicitly

When auto mode detects multiple backends, explicit selection is required.

NVIDIA Discovery
----------------

NVIDIA GPU discovery uses the nvidia-smi command-line tool.

Detection
~~~~~~~~~

if shutil.which("nvidia-smi"):
    # nvidia-smi is available
    backend = "nvidia"

**Behavior**:

- Checks for nvidia-smi executable in system PATH
- Returns "nvidia" if tool is found
- Returns None if tool is not found

Enumeration
~~~~~~~~~~~

.. code-block:: console

   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits

**Output Format**:

.. code-block:: text

   0,GPU-12345678,Tesla V100
   1,GPU-87654321,Tesla V100
   2,GPU-11111111,GeForce RTX 3090

**Parsing**:

- Splits CSV output by lines
- Splits each line by commas
- Extracts index, UUID, and name fields
- Creates GPU specification for each device

Resource Specification
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   {
       "vendor": "nvidia",
       "id": "0",
       "uuid": "GPU-12345678",
       "slots": 1,
       "name": "Tesla V100"
   }

**Fields**:

- vendor: Always "nvidia"
- id: Local device index
- uuid: Unique device identifier
- slots: Number of GPU slots (always 1)
- name: Device name from nvidia-smi

AMD Discovery
-------------

AMD GPU discovery uses either amd-smi or rocm-smi command-line tools.

Detection
~~~~~~~~~

.. code-block:: python

   if shutil.which("amd-smi") or shutil.which("rocm-smi"):
       # AMD tool is available
       backend = "amd"

**Behavior**:

- Checks for amd-smi or rocm-smi executables in system PATH
- Returns "amd" if either tool is found
- Returns None if neither tool is found

Enumeration
~~~~~~~~~~~

**Primary Method**: amd-smi list --json

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
- Extracts gpu index and uuid fields
- Normalizes UUID format (prepends "GPU-" if missing)
- Creates GPU specification for each device

**Fallback Method**: rocm-smi output parsing

.. code-block:: console

   rocm-smi

**Output Parsing**:

- Searches for patterns like "GPU[0]"
- Extracts GPU indices from output
- Uses index as both ID and UUID (no stable UUID available)
- Creates GPU specification for each found index

Resource Specification
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   {
       "vendor": "amd",
       "id": "0",
       "uuid": "GPU-12345678",
       "slots": 1
   }

**Fields**:

- vendor: Always "amd"
- id: Local device index
- uuid: Unique device identifier (or index for rocm-smi fallback)
- slots: Number of GPU slots (always 1)

Resource Pool Integration
-------------------------

Discovered GPU resources are converted to Canary's resource format:

.. code-block:: python

   {
       "id": "0",                    # Node-local runtime device ID
       "slots": 1,                   # Number of GPU slots
       "properties": {
           "vendor": "NVIDIA",         # Vendor identifier
           "uuid": "GPU-12345678",    # Unique device identifier
           "name": "Tesla V100"       # Optional: Device name
       }
   }

**Conversion Process**:

1. GPU specs returned by canary_gpu_list_gpus
2. Vendor string converted to uppercase
3. Additional properties (uuid, name, model) preserved
4. Resource ID set to local device ID
5. Slots set to specified value (default 1)
6. Added to first node's GPU resources

Resource Pool Population
------------------------

GPU resources are added to Canary's resource pool during configuration:

.. code-block:: python

   def canary_fill_gpu(config: canary.Config, pool: ResourcePool) -> None:
       node = pool.first_node()

       if node.has_resource("gpus") and node.get_resource("gpus"):
           return  # Already populated

       backend = config.get("gpu_select:.runtime:backend")
       if backend is None:
           return  # No backend selected

       gpu_specs = plugin.canary_gpu_list_gpus(config=config)
       if gpu_specs:
           node.set_resource("gpus", [converted_specs])

**Behavior**:

- Only populates first node (local node discovery)
- Skips if GPUs already present
- Skips if no backend selected
- Adds discovered GPUs to resource pool

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

- Containerized environments without GPU tools
- Custom GPU configurations
- Testing without actual hardware
- Overriding auto-discovery results

Discovery Failure Modes
-----------------------

Tool Missing
~~~~~~~~~~~~

**Symptoms**: No GPU backend detected

**Causes**:

- Vendor tools not installed
- Tools not in system PATH
- Permission issues preventing tool execution

**Solutions**:

- Install vendor tools (nvidia-smi, amd-smi, rocm-smi)
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
- Verify tool installation
- Test tool manually
- Check hardware availability
- Use manual resource definition

Invalid Output Format
~~~~~~~~~~~~~~~~~~~~~

**Symptoms**: No GPUs discovered despite tools being available

**Causes**:

- Unexpected tool output format
- Tool version incompatibility
- Parsing errors
- Invalid JSON/CSV data

**Solutions**:

- Check tool version compatibility
- Test tool output manually
- Update parsing logic if needed
- Use manual resource definition

Debugging Discovery
-------------------

To debug GPU discovery issues:

.. code-block:: console

   # Test backend detection
   python3 -m canary run --gpu-backend=auto --verbose ./tests

   # Test specific backend
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

   # Check resource pool
   python3 -m canary config show resource-pool

   # Test vendor tools manually
   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits
   amd-smi list --json
   rocm-smi

   # Check tool availability
   which nvidia-smi
   which amd-smi
   which rocm-smi

Discovery Examples
------------------

Basic Discovery
~~~~~~~~~~~~~~~

.. code-block:: console

   # Auto-detect and use available GPU backend
   python3 -m canary run --gpu-backend=auto ./tests

Explicit Backend
~~~~~~~~~~~~~~~~

.. code-block:: console

   # Use NVIDIA backend explicitly
   python3 -m canary run --gpu-backend=nvidia ./tests

   # Use AMD backend explicitly
   python3 -m canary run --gpu-backend=amd ./tests

Resource Inspection
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Check discovered GPU resources
   python3 -m canary config show resource-pool --gpu-backend=auto

Manual Override
~~~~~~~~~~~~~~~

.. code-block:: console

   # Use manual resource definition when auto-discovery fails
   python3 -m canary run --resource-pool=custom_pool.yaml ./tests

Discovery Limitations
---------------------

1. **Local Node Only**: Auto-discovery only works for local node
2. **Tool Dependence**: Requires vendor-specific tools to be installed
3. **Format Sensitivity**: Parsing depends on specific tool output formats
4. **Permission Requirements**: Tools may require specific permissions
5. **Container Limitations**: May not work in containerized environments
6. **Multi-Node**: Does not discover GPUs on remote nodes
7. **Mixed Vendors**: May require careful vendor property configuration