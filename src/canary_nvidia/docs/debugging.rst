.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Debugging NVIDIA GPU Support
=============================

Debugging NVIDIA GPU-related issues in Canary requires understanding the interaction between GPU
backend detection, resource discovery, job allocation, and runtime environment configuration.

Debugging Approach
------------------

Systematic debugging involves:

1. **Problem Identification**: Clearly define the GPU-related issue
2. **Backend Verification**: Confirm NVIDIA GPU backend detection and selection
3. **Resource Inspection**: Check GPU resource availability and allocation
4. **Environment Validation**: Verify ``CUDA_VISIBLE_DEVICES`` configuration
5. **Job Analysis**: Examine job resource requirements and execution

Common Debugging Scenarios
--------------------------

No GPU Backend Detected
~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- ``--gpu-backend=auto`` fails with "no GPU backend detected"
- ``--gpu-backend=nvidia`` fails
- No GPU resources available

**Diagnosis Steps**:

1. Check ``nvidia-smi`` availability
2. Verify installation and PATH
3. Test tool execution manually
4. Review backend detection logic

**Debugging Commands**:

.. code-block:: console

   # Check tool availability
   which nvidia-smi

   # Test tool execution
   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits

   # Check backend detection with verbose logging
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

GPU Detection but No Resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- Backend detected but no GPUs in resource pool
- GPU enumeration fails silently
- Resource pool shows no GPU resources

**Diagnosis Steps**:

1. Test ``nvidia-smi`` output format
2. Check tool execution permissions
3. Verify tool version compatibility

**Debugging Commands**:

.. code-block:: console

   # Test tool output manually
   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits

   # Check resource pool with NVIDIA backend
   python3 -m canary config show resource-pool --gpu-backend=nvidia

   # Test with verbose logging
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

GPU Resources Available but Not Allocated
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- GPUs visible in resource pool but not allocated to jobs
- Jobs fail due to insufficient GPU resources
- Resource allocation errors

**Diagnosis Steps**:

1. Check job resource requirements
2. Verify GPU request syntax
3. Review resource availability

**Debugging Commands**:

.. code-block:: console

   # Check job resource requirements
   python3 -m canary show --resources ./tests

   # Test with explicit GPU request
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 ./tests

   # Check resource pool
   python3 -m canary config show resource-pool --gpu-backend=nvidia

CUDA_VISIBLE_DEVICES Not Set
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- GPU resources allocated but ``CUDA_VISIBLE_DEVICES`` not configured
- Jobs cannot access allocated GPUs

**Diagnosis Steps**:

1. Check vendor compatibility of allocated GPUs
2. Verify user override behavior
3. Review environment variable logic

**Debugging Commands**:

.. code-block:: console

   # Test with environment variable check
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/env_check.py

   # Test without user overrides
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/simple_gpu.py

Debugging Tools
---------------

Verbose Logging
~~~~~~~~~~~~~~~

Enable verbose logging for detailed diagnostic information:

.. code-block:: console

   # Verbose backend detection
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

   # Verbose resource inspection
   python3 -m canary config show resource-pool --verbose

Tool Testing
~~~~~~~~~~~~

Test ``nvidia-smi`` manually:

.. code-block:: console

   # Basic tool check
   nvidia-smi

   # Query GPU list
   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits

   # Check tool version
   nvidia-smi --version

Resource Inspection
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Show resource pool with NVIDIA backend
   python3 -m canary config show resource-pool --gpu-backend=nvidia

   # Show job resource requirements
   python3 -m canary show --resources ./tests

Debugging Workflow
------------------

Step-by-Step Debugging
~~~~~~~~~~~~~~~~~~~~~~

1. **Verify Tool Availability**:

   .. code-block:: console

      which nvidia-smi

2. **Test Backend Detection**:

   .. code-block:: console

      python3 -m canary run --gpu-backend=nvidia --verbose ./tests

3. **Check Resource Pool**:

   .. code-block:: console

      python3 -m canary config show resource-pool --gpu-backend=nvidia

4. **Test Simple Allocation**:

   .. code-block:: console

      python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/simple.py

5. **Verify Environment**:

   .. code-block:: console

      python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/env_check.py

6. **Test Complex Scenario**:

   .. code-block:: console

      python3 -m canary run --gpu-backend=nvidia -p "gpus=2,vendor=NVIDIA" ./tests

Debugging Checklist
~~~~~~~~~~~~~~~~~~~

- [ ] Verify ``nvidia-smi`` is installed and in PATH
- [ ] Test backend detection with verbose logging
- [ ] Check resource pool population
- [ ] Verify job resource requirements
- [ ] Test ``CUDA_VISIBLE_DEVICES`` configuration
- [ ] Check vendor compatibility of allocated GPUs
- [ ] Review user override behavior
- [ ] Test with different GPU counts
- [ ] Verify multi-node behavior if applicable
- [ ] Check tool execution permissions

Common Error Patterns
---------------------

Tool Not Found
~~~~~~~~~~~~~~

**Error**: ``nvidia-smi`` not found in PATH

**Causes**:

- NVIDIA drivers/tools not installed
- Tool not in system PATH
- Permission issues

**Solutions**:

- Install NVIDIA drivers and tools
- Add ``nvidia-smi`` to PATH
- Check tool permissions
- Use manual resource definition

Invalid Tool Output
~~~~~~~~~~~~~~~~~~~

**Error**: Failed to parse ``nvidia-smi`` CSV output

**Causes**:

- Tool version incompatibility
- Unexpected output format
- Tool configuration issues

**Solutions**:

- Check tool version compatibility
- Test tool output manually
- Use manual resource definition

No GPU Resources
~~~~~~~~~~~~~~~~

**Error**: "Insufficient GPU resources" or "No GPUs available"

**Causes**:

- No GPUs detected
- GPUs filtered by vendor compatibility
- Resource pool not populated

**Solutions**:

- Verify GPU detection
- Check vendor compatibility
- Review resource pool configuration
- Use manual resource definition

CUDA_VISIBLE_DEVICES Not Configured
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Error**: ``CUDA_VISIBLE_DEVICES`` not set in job environment

**Causes**:

- No NVIDIA-compatible GPUs allocated
- User override in place
- Environment configuration failed

**Solutions**:

- Check allocated GPU vendor properties
- Review user environment variables
- Verify environment configuration logic

Advanced Debugging
------------------

Manual Resource Definition
~~~~~~~~~~~~~~~~~~~~~~~~~~

When auto-discovery fails, use manual resource definition:

.. code-block:: yaml

   # manual_gpu_pool.yaml
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

.. code-block:: console

   # Use manual resource pool
   python3 -m canary run --resource-pool=manual_gpu_pool.yaml ./tests

Isolation Technique
~~~~~~~~~~~~~~~~~~~

Isolate issues by testing components individually:

.. code-block:: console

   # Test backend detection separately
   python3 -c "import canary_nvidia; print(canary_nvidia.canary_gpu_backend_detect(None))"

   # Test GPU enumeration separately
   python3 -c "import canary_nvidia; import canary; config = canary.Config(); print(canary_nvidia.canary_gpu_list_gpus(config))"

   # Test resource pool separately
   python3 -m canary config show resource-pool --gpu-backend=nvidia

Debugging Limitations
---------------------

1. **Tool Dependency**: Debugging requires ``nvidia-smi`` to be available
2. **Hardware Dependency**: Real NVIDIA GPU hardware needed for full testing
3. **Format Sensitivity**: ``nvidia-smi`` output format affects parsing
4. **Permission Requirements**: Tool may require specific permissions
5. **Platform Differences**: Behavior may differ across platforms
6. **Container Limitations**: May not work in containerized environments without GPU passthrough
