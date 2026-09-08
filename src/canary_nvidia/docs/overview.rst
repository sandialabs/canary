.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

NVIDIA GPU Extension Overview
==============================

The ``canary_nvidia`` extension provides NVIDIA GPU backend support for Canary, enabling automatic
GPU device discovery and runtime environment configuration for NVIDIA GPUs. For AMD GPU support,
see the ``canary_amd`` plugin.

Extension Purpose
-----------------

``canary_nvidia`` is a plugin extension that implements Canary's GPU backend pattern with
NVIDIA-specific details:

- **Detection**: Uses ``nvidia-smi`` to detect NVIDIA GPU availability
- **Listing**: Enumerates NVIDIA GPU devices via ``nvidia-smi --query-gpu=index,uuid,name``
- **Environment**: Configures ``CUDA_VISIBLE_DEVICES`` for allocated GPUs
- **Integration**: Plugs into Canary's resource pool and plugin framework

Key Features
------------

1. **Automatic GPU Discovery**: Detects available NVIDIA GPU devices using ``nvidia-smi``
2. **Resource Pool Integration**: Populates Canary's resource pool with discovered GPU resources
3. **Runtime Environment Configuration**: Sets ``CUDA_VISIBLE_DEVICES`` for allocated GPUs
4. **Vendor Property Validation**: Ensures the NVIDIA environment is applied only to compatible devices
5. **User Override Support**: Respects user-set ``CUDA_VISIBLE_DEVICES``, allowing manual control
6. **Multi-Node Support**: Handles local GPU ID deduplication across multiple nodes

How It Works
------------

``canary_nvidia`` implements three plugin hooks:

1. **``canary_gpu_backend_detect``**: Checks for ``nvidia-smi`` in PATH; returns ``"nvidia"`` if found
2. **``canary_gpu_list_gpus``**: Runs ``nvidia-smi --query-gpu=index,uuid,name`` and parses CSV output
3. **``canary_runteststart``**: Sets ``CUDA_VISIBLE_DEVICES`` to the comma-separated local GPU IDs
   allocated to the job (skipped if the user already set the variable)

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
       "vendor": "NVIDIA",
       "uuid": "GPU-12345678",
       "name": "Tesla V100"
     }
   }

Vendor Compatibility
--------------------

The extension accepts GPUs whose ``vendor`` property is ``"NVIDIA"``, ``"UNKNOWN"``, or empty.
It rejects GPUs with other vendor values (e.g., ``"AMD"``, ``"ROCM"``).

Relationship to Canary
----------------------

``canary_nvidia`` is a **plugin extension**, not part of Canary core. It provides the
NVIDIA-specific implementation of device discovery and runtime environment configuration.

**What the extension DOES**:

- Detects NVIDIA GPU backend availability using ``nvidia-smi``
- Enumerates available NVIDIA GPU devices and their properties
- Populates Canary's resource pool with discovered GPU resources
- Configures ``CUDA_VISIBLE_DEVICES`` for jobs with allocated GPUs
- Integrates with Canary's topology-aware resource pool and plugin framework

**What the extension DOES NOT do**:

- Define job file formats or job specification syntax
- Execute jobs or manage job execution
- Replace or modify Canary's core resource model
- Schedule jobs or manage job queues
- Define how users request GPU resources (that is handled by job-definition extensions)

Basic Usage
-----------

.. code-block:: console

   # Use NVIDIA backend explicitly
   python3 -m canary run --gpu-backend=nvidia ./tests

   # Run tests requiring 2 GPUs
   python3 -m canary run --gpu-backend=nvidia -p gpus=2 ./tests

   # Auto-detect available GPU backend (selects NVIDIA if nvidia-smi is found)
   python3 -m canary run --gpu-backend=auto ./tests

GPU Backend Selection
---------------------

Canary supports several backend selection modes:

- **``none``** (default): No GPU backend
- **``auto``**: Automatically select available backend (fails if multiple backends are detected)
- **``nvidia``**: Use NVIDIA backend explicitly
- **``amd``**: Use AMD backend explicitly (requires ``canary_amd``)

When ``auto`` mode detects multiple backends, you must specify one explicitly.
