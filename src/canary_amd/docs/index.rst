.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Discovering AMD GPUs
====================

``canary_amd`` is a Canary plugin extension that provides AMD GPU backend support: automatic
device discovery via ``amd-smi`` (with ``rocm-smi`` fallback) and runtime environment
configuration via ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and ``CUDA_VISIBLE_DEVICES``.

**Extension type**: GPU backend, resource discovery, runtime environment adapter.

Use ``canary_amd`` when your tests request GPU resources on AMD hardware and you
want Canary to discover devices automatically and populate the runtime
environment for allocated GPUs.

Prerequisites
-------------

- AMD GPUs available on the host.
- ``amd-smi`` or ``rocm-smi`` available in ``PATH``.

Quick Start
-----------

Run tests with the AMD GPU backend:

.. code-block:: console

   canary run --gpu-backend=amd ./tests

For NVIDIA GPU support, see the ``canary_nvidia`` plugin.

.. note::

   ``canary_amd`` is a **built-in** canary extension, included in the
   ``canary-wm`` package.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   overview
   resource-discovery
   runtime-environment
   backend-hooks
   debugging
   limitations
   details

See Also
--------

- :doc:`/user/basics.resource`: Canary resource pools and allocation
- :doc:`/extensions/exts/canary_nvidia/index`: NVIDIA GPU backend
