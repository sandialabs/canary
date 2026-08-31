.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

GPU Vendor Extensions Overview
===============================

The ``canary_amd`` and ``canary_nvidia`` extensions are parallel vendor implementations of the same GPU backend pattern for Canary. Both extensions follow an analogous approach to GPU detection, listing, and runtime environment setup through Canary's plugin hooks. The shared purpose is to integrate vendor-specific GPU devices with Canary's topology-aware resource pool and configure appropriate runtime environments for jobs.

Shared GPU Backend Pattern
--------------------------

Both ``canary_amd`` and ``canary_nvidia`` implement the same fundamental pattern:

1. **GPU Detection**: Check for vendor-specific CLI tools to determine backend availability
2. **GPU Listing**: Enumerate available GPU devices using vendor tools
3. **Resource Integration**: Populate Canary's resource pool with discovered GPU resources
4. **Runtime Configuration**: Set vendor-specific visible device environment variables for allocated GPUs

This shared pattern enables consistent GPU support across different vendors while accommodating vendor-specific tools and environment requirements.

Extension Types
---------------

**canary_nvidia**: GPU backend discovery and runtime environment extension

- **Detection**: Uses ``nvidia-smi`` to detect NVIDIA GPU availability
- **Listing**: Enumerates NVIDIA GPU devices via ``nvidia-smi --query-gpu=index,uuid,name``
- **Environment**: Configures ``CUDA_VISIBLE_DEVICES`` for allocated GPUs
- **Integration**: Plugs into Canary's resource pool and plugin framework

**canary_amd**: GPU backend discovery and runtime environment extension

- **Detection**: Uses ``amd-smi`` or ``rocm-smi`` to detect AMD GPU availability
- **Listing**: Enumerates AMD GPU devices via ``amd-smi list --json`` or ``rocm-smi`` parsing
- **Environment**: Configures ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and ``CUDA_VISIBLE_DEVICES`` for allocated GPUs
- **Integration**: Plugs into Canary's resource pool and plugin framework

Key Features
------------

1. **Automatic GPU Discovery**: Detects available GPU devices using vendor-specific tools (``nvidia-smi`` for NVIDIA, ``amd-smi``/``rocm-smi`` for AMD)
2. **Resource Pool Integration**: Populates Canary's resource pool with discovered GPU resources through the shared ``canary_fill_gpu`` mechanism
3. **Runtime Environment Configuration**: Sets vendor-specific visible device environment variables through the shared ``canary_runteststart`` hook
4. **Vendor Property Validation**: Ensures correct vendor environment is applied only to compatible devices
5. **User Override Support**: Respects user-set environment variables, allowing manual control when needed
6. **Multi-Node Support**: Handles local GPU ID deduplication across multiple nodes where the same local ID may appear on different nodes

Key Features
------------

1. **Automatic GPU Discovery**: Detects available GPU devices using vendor-specific tools
2. **Resource Pool Integration**: Populates Canary's resource pool with discovered GPU resources
3. **Runtime Environment Configuration**: Sets vendor-specific visible device environment variables
4. **Vendor Property Validation**: Ensures correct vendor environment is applied to compatible devices
5. **User Override Support**: Respects user-set environment variables
6. **Multi-Node Support**: Handles local GPU ID deduplication across multiple nodes

How GPU Support Works in Canary
-------------------------------

The GPU vendor extensions implement a shared integration pattern with Canary:

1. **Shared Plugin Hooks**: Both extensions implement the same three plugin hooks:
   - ``canary_gpu_backend_detect``: Detect backend availability using vendor tools
   - ``canary_gpu_list_gpus``: List GPU devices using vendor-specific commands
   - ``canary_runteststart``: Configure runtime environment for allocated GPUs

2. **Shared Resource Integration**: Canary's core ``canary_fill_gpu`` hook calls the selected vendor's ``canary_gpu_list_gpus`` and adds results to the resource pool

3. **Shared Job Flow**: Users request GPU resources through Canary's resource requirements (e.g., ``gpus=2``), and the vendor extension handles device discovery and environment setup

4. **Vendor-Specific Implementation**: While the pattern is shared, each vendor uses different tools and environment variables:
   - NVIDIA: ``nvidia-smi`` detection, ``CUDA_VISIBLE_DEVICES`` environment
   - AMD: ``amd-smi``/``rocm-smi`` detection, ``HIP_VISIBLE_DEVICES``/``ROCR_VISIBLE_DEVICES``/``CUDA_VISIBLE_DEVICES`` environment

This shared pattern enables consistent GPU support while accommodating vendor-specific requirements.

GPU Resource Representation
---------------------------

GPU devices are represented in Canary's resource pool with the following structure:

.. code-block:: json

   {
     "id": "0",                    // Node-local runtime device ID
     "slots": 1,                   // Number of GPU slots
     "properties": {
       "vendor": "NVIDIA",         // Vendor identifier
       "uuid": "GPU-12345678",    // Unique device identifier
       "name": "Tesla V100",      // Device name (optional)
       "model": "Tesla V100"      // Device model (optional)
     }
   }

Relationship to Canary
----------------------

The GPU vendor extensions are **plugin extensions** that implement Canary's GPU backend pattern, not part of Canary core. They provide vendor-specific implementations of device discovery and runtime environment configuration:

**What the extensions DO**:

- Detect GPU backend availability using vendor-specific tools (``nvidia-smi`` for NVIDIA, ``amd-smi``/``rocm-smi`` for AMD)
- Enumerate available GPU devices and their properties
- Populate Canary's resource pool with discovered GPU resources
- Configure vendor-specific runtime environment variables for jobs with allocated GPUs
- Integrate seamlessly with Canary's topology-aware resource pool and plugin framework

**What the extensions DO NOT do**:

- Define job file formats or job specification syntax
- Execute jobs or manage job execution
- Replace or modify Canary's core resource model
- Schedule jobs or manage job queues
- Define how users request GPU resources (that's handled by job-definition extensions)

The extensions work alongside whatever job-definition extension the user chooses (e.g., ``canary_pyt``, custom extensions). Users request GPU resources through Canary's standard resource requirements system, and the vendor extensions supply the device discovery and runtime environment handling.

Basic Usage
-----------

To use GPU vendor extensions, specify the desired backend:

.. code-block:: console

   # Auto-detect available GPU backend
   python3 -m canary run --gpu-backend=auto ./tests

   # Use NVIDIA backend explicitly
   python3 -m canary run --gpu-backend=nvidia ./tests

   # Use AMD backend explicitly
   python3 -m canary run --gpu-backend=amd ./tests

   # Run tests requiring 2 GPUs
   python3 -m canary run --gpu-backend=auto -p gpus=2 ./tests

GPU Backend Selection
---------------------

Canary supports several backend selection modes:

- **``none``** (default): No GPU backend
- **``auto``**: Automatically select available backend (fails if multiple available)
- **``nvidia``**: Use NVIDIA backend explicitly
- **``amd``**: Use AMD backend explicitly

When ``auto`` mode detects multiple backends, you must specify one explicitly.

Shared Concepts
---------------

Both AMD and NVIDIA extensions share common concepts:

1. **Backend Detection**: Check for vendor-specific CLI tools
2. **GPU Enumeration**: List available devices using vendor tools
3. **Resource Integration**: Add GPUs to Canary's resource pool
4. **Runtime Configuration**: Set visible device environment variables
5. **User Override**: Respect pre-set environment variables
6. **Multi-Node Handling**: Deduplicate local GPU IDs across nodes

Vendor-Specific Differences
---------------------------

While sharing common patterns, each vendor extension has specific behaviors:

**NVIDIA**:

- Detection: ``nvidia-smi`` availability
- Enumeration: ``nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader,nounits``
- Environment: ``CUDA_VISIBLE_DEVICES``
- Vendor Properties: Accepts ``NVIDIA``, ``UNKNOWN``, or empty vendor values

**AMD**:

- Detection: ``amd-smi`` or ``rocm-smi`` availability
- Enumeration: ``amd-smi list --json`` or ``rocm-smi`` output parsing
- Environment: ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, ``CUDA_VISIBLE_DEVICES``
- Vendor Properties: Only accepts ``AMD`` or ``ROCM`` vendor values

Extension Interaction
---------------------

The GPU extensions interact with Canary through several integration points:

1. **Configuration**: ``--gpu-backend`` option selects the active backend
2. **Resource Pool**: Discovered GPUs populate the resource pool
3. **Job Selection**: Jobs request GPUs through resource requirements
4. **Runtime Setup**: Environment variables configured before job execution
5. **Result Collection**: Job results include GPU resource information

This integration enables seamless GPU support while maintaining Canary's core resource management model.

The GPU extensions provide automatic discovery and configuration for AMD and NVIDIA GPUs.
