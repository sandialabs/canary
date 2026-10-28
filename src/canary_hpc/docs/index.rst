.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_hpc:


HPC Scheduler Extension
=========================

The ``canary_hpc`` extension provides HPC scheduler and batch-execution capabilities for Canary, enabling test execution on high-performance computing systems through batch scheduling and resource management.

Use ``canary_hpc`` when you want Canary to batch jobs and submit them through
an HPC scheduler such as Slurm, PBS, Flux, or a shell backend.

Prerequisites
-------------

- A configured ``hpc_connect`` backend for the target scheduler.
- A workload that benefits from queued or batch-oriented execution.

Quick Start
-----------

Run a test suite through an HPC backend:

.. code-block:: console

   canary hpc run --backend=slurm ./tests

.. note::

   ``canary_hpc`` is a **built-in** canary extension, included in the
   ``canary-wm`` package.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   overview
   execution-model
   commands
   backends
   batch-specification
   batch-layouts
   resources
   scheduler-arguments
   timeouts
   batch-workspaces
   nested-execution
   debugging
   limitations

See Also
--------

- :doc:`/user/basics.resource`: Canary resource pool
- :doc:`/user/basics.job`: Canary job execution
- :doc:`/extensions/plugins`: Canary plugin system
- :doc:`/user/usage.hpc`: User guide for HPC batch scheduler workflows
