.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Debugging GPU Support
=====================

Debugging GPU-related issues in Canary requires understanding the interaction between GPU backend detection, resource discovery, job allocation, and runtime environment configuration.

Debugging Approach
------------------

Systematic debugging involves:

1. **Problem Identification**: Clearly define the GPU-related issue
2. **Backend Verification**: Confirm GPU backend detection and selection
3. **Resource Inspection**: Check GPU resource availability and allocation
4. **Environment Validation**: Verify runtime environment configuration
5. **Job Analysis**: Examine job resource requirements and execution

Common Debugging Scenarios
--------------------------

No GPU Backend Detected
~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- ``--gpu-backend=auto`` fails with "no GPU backend detected"
- Specific backend selection fails
- No GPU resources available

**Diagnosis Steps**:

1. Check vendor tool availability
2. Verify tool installation and PATH
3. Test tool execution manually
4. Review backend detection logic

**Debugging Commands**:

.. code-block:: console

   # Check which tools are available
   which nvidia-smi
   which amd-smi
   which rocm-smi

   # Test tool execution
   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits
   amd-smi list --json
   rocm-smi

   # Check backend detection with verbose logging
   python3 -m canary run --gpu-backend=auto --verbose ./tests

GPU Detection but No Resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- Backend detected but no GPUs in resource pool
- GPU enumeration fails silently
- Resource pool shows no GPU resources

**Diagnosis Steps**:

1. Test vendor tool output format
2. Check tool execution permissions
3. Verify tool version compatibility
4. Review parsing logic

**Debugging Commands**:

.. code-block:: console

   # Test tool output manually
   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits
   amd-smi list --json

   # Check resource pool with specific backend
   python3 -m canary config show resource-pool --gpu-backend=nvidia
   python3 -m canary config show resource-pool --gpu-backend=amd

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
4. Examine allocation constraints

**Debugging Commands**:

.. code-block:: console

   # Check job resource requirements
   python3 -m canary show --resources ./tests

   # Test with explicit GPU request
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 ./tests

   # Check resource pool
   python3 -m canary config show resource-pool --gpu-backend=nvidia

Environment Variables Not Set
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- GPU resources allocated but environment variables not configured
- Jobs cannot access allocated GPUs
- Missing CUDA_VISIBLE_DEVICES, HIP_VISIBLE_DEVICES, etc.

**Diagnosis Steps**:

1. Check vendor compatibility of allocated GPUs
2. Verify user override behavior
3. Review environment variable logic
4. Test with simple job

**Debugging Commands**:

.. code-block:: console

   # Test with environment variable check
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/env_check.py

   # Check allocated resources
   python3 -m canary show --resources tests/gpu_test.py

   # Test without user overrides
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/simple_gpu.py

Debugging Tools
---------------

Verbose Logging
~~~~~~~~~~~~~~~

Enable verbose logging for detailed diagnostic information:

.. code-block:: console

   # Verbose backend detection
   python3 -m canary run --gpu-backend=auto --verbose ./tests

   # Verbose test run
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

   # Verbose resource inspection
   python3 -m canary config show resource-pool --verbose

Log Analysis
~~~~~~~~~~~~

Analyze logs for GPU-related messages:

.. code-block:: console

   # Check Canary logs
   tail -f ~/.canary/logs/gpu.log

   # Filter GPU-related messages
   grep -i "gpu\|nvidia\|amd" ~/.canary/logs/canary.log

   # Check specific log levels
   python3 -m canary run --gpu-backend=nvidia --log-level=DEBUG ./tests

Resource Inspection
~~~~~~~~~~~~~~~~~~~

Inspect GPU resources and allocation:

.. code-block:: console

   # Show resource pool with GPU backend
   python3 -m canary config show resource-pool --gpu-backend=nvidia

   # Show job resource requirements
   python3 -m canary show --resources ./tests

   # Show allocated resources for specific test
   python3 -m canary show --resources tests/gpu_test.py

Tool Testing
~~~~~~~~~~~~

Test vendor tools manually:

.. code-block:: console

   # Test NVIDIA tools
   nvidia-smi
   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits

   # Test AMD tools
   amd-smi
   amd-smi list --json
   rocm-smi

   # Check tool versions
   nvidia-smi --version
   amd-smi --version
   rocm-smi --version

Debugging Workflow
------------------

Step-by-Step Debugging
~~~~~~~~~~~~~~~~~~~~~~

1. **Verify Tool Availability**:

   .. code-block:: console

      which nvidia-smi amd-smi rocm-smi

2. **Test Backend Detection**:

   .. code-block:: console

      python3 -m canary run --gpu-backend=auto --verbose ./tests

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

- [ ] Verify vendor tools are installed and in PATH
- [ ] Test backend detection with verbose logging
- [ ] Check resource pool population
- [ ] Verify job resource requirements
- [ ] Test environment variable configuration
- [ ] Check vendor compatibility of allocated GPUs
- [ ] Review user override behavior
- [ ] Test with different GPU counts
- [ ] Verify multi-node behavior if applicable
- [ ] Check tool execution permissions

Common Error Patterns
---------------------

Tool Not Found
~~~~~~~~~~~~~~

**Error**: "nvidia-smi not found", "amd-smi not found"

**Causes**:

- Vendor tools not installed
- Tools not in system PATH
- Permission issues

**Solutions**:

- Install vendor drivers and tools
- Add tools to PATH
- Check tool permissions
- Use manual resource definition

Invalid Tool Output
~~~~~~~~~~~~~~~~~~~

**Error**: "Failed to parse GPU output", "Invalid JSON/CSV format"

**Causes**:

- Tool version incompatibility
- Unexpected output format
- Tool configuration issues

**Solutions**:

- Check tool version compatibility
- Test tool output manually
- Update parsing logic if needed
- Use manual resource definition

No GPU Resources
~~~~~~~~~~~~~~~~

**Error**: "Insufficient GPU resources", "No GPUs available"

**Causes**:

- No GPUs detected
- GPUs filtered by vendor compatibility
- Resource pool not populated

**Solutions**:

- Verify GPU detection
- Check vendor compatibility
- Review resource pool configuration
- Use manual resource definition

Environment Not Configured
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Error**: "CUDA_VISIBLE_DEVICES not set", "No visible devices"

**Causes**:

- No compatible GPUs allocated
- User override in place
- Environment configuration failed

**Solutions**:

- Check allocated GPU vendor properties
- Review user environment variables
- Verify environment configuration logic

Debugging Examples
------------------

NVIDIA Debugging
~~~~~~~~~~~~~~~~

.. code-block:: console

   # Check NVIDIA backend detection
   python3 -m canary run --gpu-backend=nvidia --verbose ./tests

   # Test nvidia-smi manually
   nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits

   # Check resource pool
   python3 -m canary config show resource-pool --gpu-backend=nvidia

   # Test with explicit GPU request
   python3 -m canary run --gpu-backend=nvidia -p gpus=2 tests/gpu_test.py

AMD Debugging
~~~~~~~~~~~~~

.. code-block:: console

   # Check AMD backend detection
   python3 -m canary run --gpu-backend=amd --verbose ./tests

   # Test amd-smi manually
   amd-smi list --json

   # Test rocm-smi manually
   rocm-smi

   # Check resource pool
   python3 -m canary config show resource-pool --gpu-backend=amd

   # Test with explicit GPU request
   python3 -m canary run --gpu-backend=amd -p gpus=2 tests/gpu_test.py

Mixed Vendor Debugging
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Check which backends are available
   python3 -m canary run --gpu-backend=auto --verbose ./tests

   # Test vendor-specific allocation
   python3 -m canary run --gpu-backend=auto -p "gpus=1,vendor=NVIDIA" ./tests
   python3 -m canary run --gpu-backend=auto -p "gpus=1,vendor=AMD" ./tests

   # Check resource pool with mixed vendors
   python3 -m canary config show resource-pool --gpu-backend=auto

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

Environment Variable Testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Test environment variable configuration:

.. code-block:: python

   # tests/env_check.py
   import os

   def test_gpu_environment():
       cuda = os.environ.get("CUDA_VISIBLE_DEVICES", "")
       hip = os.environ.get("HIP_VISIBLE_DEVICES", "")
       rocr = os.environ.get("ROCR_VISIBLE_DEVICES", "")

       print(f"CUDA_VISIBLE_DEVICES: {cuda}")
       print(f"HIP_VISIBLE_DEVICES: {hip}")
       print(f"ROCR_VISIBLE_DEVICES: {rocr}")

       assert cuda or hip or rocr, "No GPU environment variables set"

.. code-block:: console

   # Test environment variables
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/env_check.py

Vendor Compatibility Testing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Test vendor compatibility and selection:

.. code-block:: python

   # tests/vendor_check.py
   def test_vendor_compatibility():
       import canary
       from canary import job

       # Create fake job with different vendor properties
       case = job.Job()
       case.resources = {
           "gpus": [
               {"id": "0", "properties": {"vendor": "NVIDIA"}},
               {"id": "1", "properties": {"vendor": "AMD"}},
           ]
       }
       case.variables = {}

       # Test NVIDIA selection
       import canary_nvidia
       canary_nvidia.canary_runteststart(case)
       assert "CUDA_VISIBLE_DEVICES" in case.variables

       # Test AMD selection
       case.variables = {}
       import canary_amd
       canary_amd.canary_runteststart(case)
       assert "HIP_VISIBLE_DEVICES" in case.variables

.. code-block:: console

   # Test vendor compatibility
   python3 -m canary run tests/vendor_check.py

Debugging Best Practices
------------------------

Isolation Technique
~~~~~~~~~~~~~~~~~~~

Isolate GPU issues by testing components individually:

.. code-block:: console

   # Test backend detection separately
   python3 -c "import canary_nvidia; print(canary_nvidia.canary_gpu_backend_detect(None))"

   # Test GPU enumeration separately
   python3 -c "import canary_nvidia; import canary; config = canary.Config(); print(canary_nvidia.canary_gpu_list_gpus(config))"

   # Test resource pool separately
   python3 -m canary config show resource-pool --gpu-backend=nvidia

Divide and Conquer
~~~~~~~~~~~~~~~~~~

Break down complex GPU issues:

1. Test backend detection
2. Test resource discovery
3. Test job allocation
4. Test environment configuration
5. Test job execution

Minimal Reproduction
~~~~~~~~~~~~~~~~~~~~

Create minimal test cases:

.. code-block:: console

   # Test with minimal test
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/minimal.py

   # Test with simple resource requirement
   python3 -m canary run --gpu-backend=nvidia tests/simple_gpu.py

Gradual Complexity
~~~~~~~~~~~~~~~~~~

Increase complexity gradually:

.. code-block:: console

   # Start simple
   python3 -m canary run --gpu-backend=nvidia -p gpus=1 tests/simple.py

   # Add complexity
   python3 -m canary run --gpu-backend=nvidia -p "gpus=2,vendor=NVIDIA" tests/medium.py

   # Full complexity
   python3 -m canary run --gpu-backend=nvidia -p "gpus=4" ./tests

Debugging Limitations
---------------------

1. **Tool Dependency**: Debugging requires vendor tools to be available
2. **Hardware Dependency**: Real GPU hardware needed for full testing
3. **Format Sensitivity**: Tool output format affects parsing
4. **Permission Requirements**: Tools may require specific permissions
5. **Platform Differences**: Behavior may differ across platforms
6. **Container Limitations**: May not work in containerized environments
7. **Multi-Vendor Complexity**: Mixed vendor systems add complexity

Debugging Resources
-------------------

- Canary GPU extension documentation
- Vendor tool documentation (nvidia-smi, amd-smi, rocm-smi)
- Canary core resource pool documentation
- Canary plugin system documentation
- Community forums and support channels