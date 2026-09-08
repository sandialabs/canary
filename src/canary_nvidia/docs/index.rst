.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

canary_nvidia Documentation
============================

``canary_nvidia`` is a Canary plugin extension that provides NVIDIA GPU backend support:
automatic device discovery via ``nvidia-smi`` and runtime environment configuration via
``CUDA_VISIBLE_DEVICES``.

For AMD GPU support, see the ``canary_amd`` plugin.

.. note::

   ``canary_nvidia`` is a **built-in** canary extension, included in the
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
