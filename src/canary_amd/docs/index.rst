.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

canary_amd Documentation
=========================

``canary_amd`` is a Canary plugin extension that provides AMD GPU backend support: automatic
device discovery via ``amd-smi`` (with ``rocm-smi`` fallback) and runtime environment
configuration via ``HIP_VISIBLE_DEVICES``, ``ROCR_VISIBLE_DEVICES``, and ``CUDA_VISIBLE_DEVICES``.

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
