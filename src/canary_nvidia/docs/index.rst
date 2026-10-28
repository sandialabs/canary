.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Discovering NVIDIA GPUs
=======================

``canary_nvidia`` is a Canary plugin extension that provides NVIDIA GPU backend support:
automatic device discovery via ``nvidia-smi`` and runtime environment configuration via
``CUDA_VISIBLE_DEVICES``.

**Extension type**: GPU backend, resource discovery, runtime environment adapter.

Use ``canary_nvidia`` when your tests request GPU resources on NVIDIA hardware
and you want Canary to discover devices automatically and populate the runtime
environment for allocated GPUs.

Prerequisites
-------------

- NVIDIA GPUs available on the host.
- ``nvidia-smi`` available in ``PATH``.

Quick Start
-----------

Run tests with the NVIDIA GPU backend:

.. code-block:: console

   canary run --gpu-backend=nvidia ./tests

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

See Also
--------

- :doc:`/user/basics.resource`: Canary resource pools and allocation
- :doc:`/extensions/exts/canary_amd/index`: AMD GPU backend
