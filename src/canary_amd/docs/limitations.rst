.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

AMD GPU Extension Limitations
==============================

``canary_amd`` has several important limitations that users should be aware of when working with
AMD GPU resources in Canary.

Architectural Limitations
--------------------------

Tool Dependency
~~~~~~~~~~~~~~~

**Limitation**: Requires ``amd-smi`` or ``rocm-smi`` to be installed and in PATH

**Impact**:

- Extension fails silently if neither tool is available
- ``rocm-smi`` fallback provides less information than ``amd-smi`` (no stable UUIDs)

**Workaround**:

- Install the AMD ROCm stack (which includes ``amd-smi`` and/or ``rocm-smi``)
- Ensure tools are in system PATH
- Prefer ``amd-smi`` over ``rocm-smi`` for more reliable UUID information
- Use manual resource definition when tools are unavailable

Local Node Only
~~~~~~~~~~~~~~~

**Limitation**: GPU discovery only works for the local node

**Impact**:

- Does not discover GPUs on remote nodes
- Multi-node systems require manual resource definition
- HPC environments may need custom resource pool configuration
- ``canary_fill_gpu`` only populates the first (local) node

**Workaround**:

- Use manual resource definition for remote nodes
- Configure resource pool for multi-node environments

Format Sensitivity
~~~~~~~~~~~~~~~~~~

**Limitation**: Parsing depends on the specific tool output formats

**Impact**:

- ``amd-smi`` tool version changes may break JSON parsing
- ``rocm-smi`` output format is not standardized; regex parsing is best-effort
- Parsing errors result in no GPU resources being discovered

**Workaround**:

- Test with your specific tool versions
- Use ``amd-smi`` where possible (structured JSON output)
- Use manual resource definition for problematic formats

rocm-smi Fallback Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: ``rocm-smi`` fallback does not provide stable UUIDs

**Impact**:

- UUID is set to the device index (not a real UUID)
- Resource uniqueness identification may be less reliable

**Workaround**:

- Install ``amd-smi`` for proper UUID support
- Use manual resource definition with explicit UUIDs

Environment Configuration Limitations
--------------------------------------

User Override Priority
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: If **any** of ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, or
``CUDA_VISIBLE_DEVICES`` is already set, none of them are configured automatically

**Impact**:

- Extension cannot override user configurations
- May prevent automatic environment setup
- No validation of user-set variables

**Workaround**:

- Document environment variable behavior
- Test with a clean environment when debugging
- Unset all three variables to allow automatic configuration

Vendor Compatibility Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Only accepts ``AMD`` or ``ROCM`` vendor values; does not claim ``UNKNOWN`` devices

**Impact**:

- GPUs with ``UNKNOWN``, empty, or ``NVIDIA`` vendor values are ignored
- ``UNKNOWN`` devices fall through to ``canary_nvidia`` for handling
- Mixed vendor systems require careful configuration

**Workaround**:

- Set correct vendor properties in resource pool (``AMD`` or ``ROCM``)
- Use explicit vendor specification in job requirements (e.g., ``-p "gpus=1,vendor=AMD"``)

Multi-Node Limitations
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Limited multi-node GPU support

**Impact**:

- Local GPU ID deduplication only
- No global GPU ID coordination
- Multi-node allocations may have duplicate local IDs

**Workaround**:

- Use manual resource definition for multi-node
- Configure unique local IDs across nodes

Performance Limitations
-----------------------

Discovery Overhead
~~~~~~~~~~~~~~~~~~

**Limitation**: GPU discovery adds configuration overhead

**Impact**:

- Tool execution adds startup time
- When ``amd-smi`` fails, ``rocm-smi`` is also tried, adding further overhead
- Discovery runs on every Canary invocation

**Workaround**:

- Use manual resource definition for static environments
- Ensure ``amd-smi`` works correctly to avoid fallback overhead

Resource Utilization Tracking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: No GPU utilization monitoring

**Impact**:

- No GPU utilization monitoring
- No performance metrics collection
- No historical utilization data

**Workaround**:

- Use external monitoring tools (e.g., ``amd-smi monitor``, ``rocm-smi``)

Feature Limitations
--------------------

Missing Features
~~~~~~~~~~~~~~~~

**Limitation**: Some advanced features are not implemented

**Impact**:

- No GPU health monitoring
- No GPU temperature monitoring
- No GPU power management
- Basic error handling only

**Workaround**:

- Use ``amd-smi`` or ``rocm-smi`` directly for monitoring

Error Handling Limitations
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Silent failure modes

**Impact**:

- Limited automatic error recovery
- Basic error reporting via ``logger.debug``
- No comprehensive error validation

**Workaround**:

- Implement robust error handling in tests
- Monitor for error conditions
- Test error scenarios thoroughly

Compatibility Limitations
--------------------------

Platform Compatibility
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Platform-specific behavior

**Impact**:

- ``amd-smi``/``rocm-smi`` availability varies by platform and ROCm installation
- Permission requirements may vary
- May not work in containerized environments without GPU passthrough

**Workaround**:

- Test across target platforms
- Document platform and ROCm version requirements

Version Compatibility
~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Tool version-specific output format

**Impact**:

- ``amd-smi`` version changes may alter JSON structure
- ``rocm-smi`` output varies widely across versions

**Workaround**:

- Document supported ROCm and tool versions
- Test with multiple tool versions

Limitations Summary
-------------------

``canary_amd`` provides essential AMD GPU support for Canary but has important limitations
requiring careful consideration in test design and execution planning. Key constraints:

- Requires ``amd-smi`` or ``rocm-smi`` in PATH
- Discovers local node GPUs only
- Sets ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and ``CUDA_VISIBLE_DEVICES``
- Does not claim ``UNKNOWN`` vendor devices (those fall through to ``canary_nvidia``)
- ``rocm-smi`` fallback lacks stable UUIDs
- Silent failure on tool or parsing errors
