.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

NVIDIA GPU Extension Limitations
==================================

``canary_nvidia`` has several important limitations that users should be aware of when working
with NVIDIA GPU resources in Canary.

Architectural Limitations
--------------------------

Tool Dependency
~~~~~~~~~~~~~~~

**Limitation**: Requires ``nvidia-smi`` to be installed and in PATH

**Impact**:

- Extension fails silently if ``nvidia-smi`` is not available
- No fallback to alternative NVIDIA discovery methods

**Workaround**:

- Install NVIDIA drivers and tools (which include ``nvidia-smi``)
- Ensure ``nvidia-smi`` is in system PATH
- Use manual resource definition when the tool is unavailable

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

**Limitation**: Parsing depends on the specific ``nvidia-smi`` CSV output format

**Impact**:

- Tool version changes may break parsing
- Unexpected output formats cause failures
- Parsing errors result in no GPU resources being discovered

**Workaround**:

- Test with your specific ``nvidia-smi`` version
- Use manual resource definition for problematic formats
- Document supported tool versions

Environment Configuration Limitations
--------------------------------------

User Override Priority
~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: User-set ``CUDA_VISIBLE_DEVICES`` always takes precedence

**Impact**:

- Extension cannot override user configurations
- May prevent automatic environment setup
- No validation of user-set variables

**Workaround**:

- Document environment variable behavior
- Test with a clean environment when debugging
- Use explicit variable configuration

Vendor Compatibility Constraints
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: Specific vendor compatibility requirements

**Impact**:

- Accepts only ``NVIDIA``, ``UNKNOWN``, or empty vendor values
- GPU resources with other vendor values (e.g., ``AMD``, ``ROCM``) are ignored

**Workaround**:

- Set correct vendor properties in resource pool
- Use explicit vendor specification in job requirements (e.g., ``-p "gpus=1,vendor=NVIDIA"``)

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

- ``nvidia-smi`` execution adds startup time
- Discovery runs on every Canary invocation

**Workaround**:

- Use manual resource definition for static environments

Resource Utilization Tracking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Limitation**: No GPU utilization monitoring

**Impact**:

- No GPU utilization monitoring
- No performance metrics collection
- No historical utilization data

**Workaround**:

- Use external monitoring tools (e.g., ``nvidia-smi dmon``)

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

- Use ``nvidia-smi`` directly for monitoring
- Document feature limitations

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

- ``nvidia-smi`` availability varies by platform and driver installation
- Permission requirements may vary
- May not work in containerized environments without GPU passthrough

**Workaround**:

- Test across target platforms
- Document platform requirements

Version Compatibility
~~~~~~~~~~~~~~~~~~~~~

**Limitation**: ``nvidia-smi`` version-specific output format

**Impact**:

- Tool version changes may break CSV parsing
- Old tool versions may produce different output

**Workaround**:

- Document supported tool versions
- Test with multiple ``nvidia-smi`` versions

Limitations Summary
-------------------

``canary_nvidia`` provides essential NVIDIA GPU support for Canary but has important limitations
requiring careful consideration in test design and execution planning. Key constraints:

- Requires ``nvidia-smi`` in PATH
- Discovers local node GPUs only
- Sets only ``CUDA_VISIBLE_DEVICES``
- Does not claim ``UNKNOWN`` devices for NVIDIA if another vendor is detected first
- Silent failure on tool or parsing errors
