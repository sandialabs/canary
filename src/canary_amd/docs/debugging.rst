.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Debugging AMD GPU Support
==========================

Debugging AMD GPU-related issues in Canary requires understanding the interaction between GPU
backend detection, resource discovery, job allocation, and runtime environment configuration.

Debugging Approach
------------------

Systematic debugging involves:

1. **Problem Identification**: Clearly define the GPU-related issue
2. **Backend Verification**: Confirm AMD GPU backend detection and selection
3. **Resource Inspection**: Check GPU resource availability and allocation
4. **Environment Validation**: Verify ``HIP_VISIBLE_DEVICES``/``ROCR_VISIBLE_DEVICES``/
   ``CUDA_VISIBLE_DEVICES`` configuration
5. **Job Analysis**: Examine job resource requirements and execution

Common Debugging Scenarios
--------------------------

No GPU Backend Detected
~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- ``--gpu-backend=auto`` fails with "no GPU backend detected"
- ``--gpu-backend=amd`` fails
- No GPU resources available

**Diagnosis Steps**:

1. Check ``amd-smi`` and ``rocm-smi`` availability
2. Verify installation and PATH
3. Test tool execution manually
4. Review backend detection logic

**Debugging Commands**:

.. code-block:: console

   # Check tool availability
   which amd-smi
   which rocm-smi

   # Test tool execution
   amd-smi list --json
   rocm-smi

   # Check backend detection with verbose logging
   python3 -m canary run --gpu-backend=amd --verbose ./tests

GPU Detection but No Resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- Backend detected but no GPUs in resource pool
- GPU enumeration fails silently
- Resource pool shows no GPU resources

**Diagnosis Steps**:

1. Test ``amd-smi``/``rocm-smi`` output format
2. Check tool execution permissions
3. Verify tool version compatibility

**Debugging Commands**:

.. code-block:: console

   # Test primary tool output manually
   amd-smi list --json

   # Test fallback tool manually
   rocm-smi

   # Check resource pool with AMD backend
   python3 -m canary config show resource-pool --gpu-backend=amd

   # Test with verbose logging
   python3 -m canary run --gpu-backend=amd --verbose ./tests

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
   python3 -m canary run --gpu-backend=amd -p gpus=1 ./tests

   # Check resource pool
   python3 -m canary config show resource-pool --gpu-backend=amd

AMD Environment Variables Not Set
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

- GPU resources allocated but ``HIP_VISIBLE_DEVICES``/``ROCR_VISIBLE_DEVICES``/
  ``CUDA_VISIBLE_DEVICES`` not configured
- Jobs cannot access allocated GPUs

**Diagnosis Steps**:

1. Check vendor compatibility of allocated GPUs (must be ``AMD`` or ``ROCM``)
2. Verify user override behavior (check if any of the three variables is pre-set)
3. Review environment variable logic

**Debugging Commands**:

.. code-block:: console

   # Test with environment variable check
   python3 -m canary run --gpu-backend=amd -p gpus=1 tests/env_check.py

   # Test without user overrides
   python3 -m canary run --gpu-backend=amd -p gpus=1 tests/simple_gpu.py

Debugging Tools
---------------

Verbose Logging
~~~~~~~~~~~~~~~

Enable verbose logging for detailed diagnostic information:

.. code-block:: console

   # Verbose backend detection
   python3 -m canary run --gpu-backend=amd --verbose ./tests

   # Verbose resource inspection
   python3 -m canary config show resource-pool --verbose

Tool Testing
~~~~~~~~~~~~

Test AMD tools manually:

.. code-block:: console

   # Test amd-smi (primary)
   amd-smi list --json

   # Test rocm-smi (fallback)
   rocm-smi

   # Check tool versions
   amd-smi --version
   rocm-smi --version

Resource Inspection
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Show resource pool with AMD backend
   python3 -m canary config show resource-pool --gpu-backend=amd

   # Show job resource requirements
   python3 -m canary show --resources ./tests

Debugging Workflow
------------------

Step-by-Step Debugging
~~~~~~~~~~~~~~~~~~~~~~

1. **Verify Tool Availability**:

   .. code-block:: console

      which amd-smi rocm-smi

2. **Test Backend Detection**:

   .. code-block:: console

      python3 -m canary run --gpu-backend=amd --verbose ./tests

3. **Check Resource Pool**:

   .. code-block:: console

      python3 -m canary config show resource-pool --gpu-backend=amd

4. **Test Simple Allocation**:

   .. code-block:: console

      python3 -m canary run --gpu-backend=amd -p gpus=1 tests/simple.py

5. **Verify Environment**:

   .. code-block:: console

      python3 -m canary run --gpu-backend=amd -p gpus=1 tests/env_check.py

6. **Test Complex Scenario**:

   .. code-block:: console

      python3 -m canary run --gpu-backend=amd -p "gpus=2,vendor=AMD" ./tests

Debugging Checklist
~~~~~~~~~~~~~~~~~~~

- [ ] Verify ``amd-smi`` or ``rocm-smi`` is installed and in PATH
- [ ] Test backend detection with verbose logging
- [ ] Check resource pool population
- [ ] Verify job resource requirements
- [ ] Test ``HIP_VISIBLE_DEVICES``/``ROCR_VISIBLE_DEVICES``/``CUDA_VISIBLE_DEVICES`` configuration
- [ ] Check vendor compatibility of allocated GPUs (must be ``AMD`` or ``ROCM``)
- [ ] Review user override behavior
- [ ] Test with different GPU counts
- [ ] Verify multi-node behavior if applicable
- [ ] Check tool execution permissions

Common Error Patterns
---------------------

Tools Not Found
~~~~~~~~~~~~~~~

**Error**: Neither ``amd-smi`` nor ``rocm-smi`` found in PATH

**Causes**:

- AMD ROCm stack not installed
- Tools not in system PATH
- Permission issues

**Solutions**:

- Install AMD ROCm stack
- Add tools to PATH
- Check tool permissions
- Use manual resource definition

Invalid Tool Output
~~~~~~~~~~~~~~~~~~~

**Error**: Failed to parse ``amd-smi`` JSON or ``rocm-smi`` output

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
- GPUs filtered by vendor compatibility (e.g., resources have ``vendor=NVIDIA``)
- Resource pool not populated

**Solutions**:

- Verify GPU detection with ``amd-smi list --json``
- Check vendor properties of discovered GPUs
- Review resource pool configuration
- Use manual resource definition

AMD Environment Variables Not Configured
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Error**: ``HIP_VISIBLE_DEVICES`` not set in job environment

**Causes**:

- No AMD/ROCM-compatible GPUs allocated
- User override in place (any of the three variables already set)
- Environment configuration failed

**Solutions**:

- Check allocated GPU vendor properties (must be ``AMD`` or ``ROCM``)
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
                 vendor: "AMD"
                 uuid: "GPU-12345678"
             - id: "1"
               slots: 1
               properties:
                 vendor: "AMD"
                 uuid: "GPU-87654321"

.. code-block:: console

   # Use manual resource pool
   python3 -m canary run --resource-pool=manual_gpu_pool.yaml ./tests

Isolation Technique
~~~~~~~~~~~~~~~~~~~

Isolate issues by testing components individually:

.. code-block:: console

   # Test backend detection separately
   python3 -c "import canary_amd; print(canary_amd.canary_gpu_backend_detect(None))"

   # Test GPU enumeration separately
   python3 -c "import canary_amd; import canary; config = canary.Config(); print(canary_amd.canary_gpu_list_gpus(config))"

   # Test resource pool separately
   python3 -m canary config show resource-pool --gpu-backend=amd

Debugging Limitations
---------------------

1. **Tool Dependency**: Debugging requires ``amd-smi`` or ``rocm-smi`` to be available
2. **Hardware Dependency**: Real AMD GPU hardware needed for full testing
3. **Format Sensitivity**: Tool output format affects parsing
4. **UUID Availability**: ``rocm-smi`` fallback does not provide stable UUIDs
5. **Permission Requirements**: Tools may require specific permissions
6. **Platform Differences**: Behavior may differ across platforms
7. **Container Limitations**: May not work in containerized environments without GPU passthrough
