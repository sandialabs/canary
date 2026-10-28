.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_flux:

Flux Extension
==============

The ``canary_flux`` extension provides **Flux Framework integration** for Canary, enabling test execution on Flux-based HPC systems through direct Flux allocation and job submission.

Use ``canary_flux`` when you want direct Flux execution of individual Canary
jobs inside a Flux allocation rather than the batch-oriented workflow provided
by ``canary_hpc``.

Prerequisites
-------------

- A configured Flux backend through ``hpc_connect``.
- A Flux-based environment where direct allocation and submission are
  appropriate.

Quick Start
-----------

Run a test suite through Flux directly:

.. code-block:: console

   canary flux run ./tests

.. note::

   ``canary_flux`` is a **built-in** canary extension, included in the
   ``canary-wm`` package.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   overview
   commands
   execution-model
   flux-job-lifecycle
   resource-management
   backends
   timeouts
   timing-metrics
   debugging
   limitations

See Also
--------

- :doc:`/user/basics.resource`: Canary resource pool
- :doc:`/user/basics.job`: Canary job execution
- :doc:`/extensions/plugins`: Canary plugin system
- :doc:`/extensions/exts/canary_hpc/index`: ``canary_hpc`` extension for batch-oriented Flux execution
