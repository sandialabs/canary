.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

AMD GPU Extension Overview
===========================

The ``canary_amd`` extension provides AMD GPU backend support for Canary, enabling automatic GPU
device discovery and runtime environment configuration for AMD GPUs. For NVIDIA GPU support, see
the ``canary_nvidia`` plugin.

Extension Purpose
-----------------

``canary_amd`` is a plugin extension that implements Canary's GPU backend pattern with AMD-specific
details:

- **Detection**: Uses ``amd-smi`` or ``rocm-smi`` to detect AMD GPU availability
- **Listing**: Enumerates AMD GPU devices via ``amd-smi list --json`` or ``rocm-smi`` parsing
- **Environment**: Configures ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and
  ``CUDA_VISIBLE_DEVICES`` for allocated GPUs
- **Integration**: Plugs into Canary's resource pool and plugin framework

Key Features
------------

1. **Automatic GPU Discovery**: Detects available AMD GPU devices using ``amd-smi`` or ``rocm-smi``
2. **Resource Pool Integration**: Populates Canary's resource pool with discovered GPU resources
3. **Runtime Environment Configuration**: Sets ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``,
   and ``CUDA_VISIBLE_DEVICES`` for allocated GPUs
4. **Vendor Property Validation**: Ensures AMD environment is applied only to AMD/ROCM-compatible
   devices
5. **User Override Support**: Respects any pre-set visible-devices variable, allowing manual control
6. **Multi-Node Support**: Handles local GPU ID deduplication across multiple nodes
7. **Fallback Discovery**: Falls back from ``amd-smi`` to ``rocm-smi`` if needed

How It Works
------------

``canary_amd`` implements three plugin hooks:

1. **``canary_gpu_backend_detect``**: Checks for ``amd-smi`` or ``rocm-smi`` in PATH; returns
   ``"amd"`` if either is found
2. **``canary_gpu_list_gpus``**: Tries ``amd-smi list --json`` first; falls back to ``rocm-smi``
   output parsing if that fails
3. **``canary_runteststart``**: Sets ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and
   ``CUDA_VISIBLE_DEVICES`` to the comma-separated local GPU IDs allocated to the job (skipped
   if the user already set any of these variables)

Canary's core ``canary_fill_gpu`` hook calls ``canary_gpu_list_gpus`` and adds results to the
resource pool.

GPU Resource Representation
---------------------------

GPU devices are represented in Canary's resource pool with the following structure:

.. code-block:: json

   {
     "id": "0",
     "slots": 1,
     "properties": {
       "vendor": "AMD",
       "uuid": "GPU-12345678"
     }
   }

Vendor Compatibility
--------------------

The extension accepts GPUs whose ``vendor`` property is ``"AMD"`` or ``"ROCM"``.
It rejects GPUs with other vendor values (e.g., ``"NVIDIA"``, ``"UNKNOWN"``, or empty string).
This means ``UNKNOWN`` devices fall through to ``canary_nvidia`` for handling.

Relationship to Canary
----------------------

``canary_amd`` is a **plugin extension**, not part of Canary core. It provides the AMD-specific
implementation of device discovery and runtime environment configuration.

**What the extension DOES**:

- Detects AMD GPU backend availability using ``amd-smi`` or ``rocm-smi``
- Enumerates available AMD GPU devices and their properties
- Populates Canary's resource pool with discovered GPU resources
- Configures ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and ``CUDA_VISIBLE_DEVICES``
  for jobs with allocated AMD GPUs
- Integrates with Canary's topology-aware resource pool and plugin framework

**What the extension DOES NOT do**:

- Define job file formats or job specification syntax
- Execute jobs or manage job execution
- Replace or modify Canary's core resource model
- Schedule jobs or manage job queues
- Define how users request GPU resources (that is handled by job-definition extensions)
- Claim ``UNKNOWN`` vendor devices (those fall through to ``canary_nvidia``)

Basic Usage
-----------

.. code-block:: console

   # Use AMD backend explicitly
   python3 -m canary run --gpu-backend=amd ./tests

   # Run tests requiring 2 GPUs
   python3 -m canary run --gpu-backend=amd -p gpus=2 ./tests

   # Auto-detect available GPU backend (selects AMD if amd-smi or rocm-smi is found)
   python3 -m canary run --gpu-backend=auto ./tests

GPU Backend Selection
---------------------

Canary supports several backend selection modes:

- **``none``** (default): No GPU backend
- **``auto``**: Automatically select available backend (fails if multiple backends are detected)
- **``amd``**: Use AMD backend explicitly
- **``nvidia``**: Use NVIDIA backend explicitly (requires ``canary_nvidia``)

When ``auto`` mode detects multiple backends, you must specify one explicitly.
