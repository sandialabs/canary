.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

HPC Scheduler Extension Overview
================================

``canary_hpc`` lets Canary batch jobs and submit them through an HPC scheduler.
Use it when your test or workflow run needs queue-backed execution on systems
managed by Slurm, PBS, Flux, or another ``hpc_connect`` backend.

What It Does
------------

``canary_hpc`` changes how Canary runs jobs after collection and selection:

- Canary still discovers tests, resolves dependencies, and builds job specs in
  the usual way.
- ``canary_hpc`` groups selected jobs into batches.
- Each batch is submitted through an ``hpc_connect`` backend.
- Canary then runs again inside the allocated batch workspace to execute the
  jobs assigned to that batch.

This is the right workflow when queue submission and batch packing are more
important than immediate local execution.

What It Does Not Change
-----------------------

``canary_hpc`` does not define job file formats. You still describe jobs with
the usual generators, such as ``canary_pyt``, ``canary_vvtest``, or
``canary_cmake``.

It also does not replace Canary's resource model. Jobs still request CPUs,
GPUs, nodes, and other resources in the normal Canary way. The difference is
that ``canary_hpc`` builds the usable resource pool from the selected
``hpc_connect`` backend and from the batch allocation that backend creates.

First Commands
--------------

.. code-block:: console

   # Inspect a backend before running anything
   canary hpc info slurm

   # Submit a test suite through a scheduler backend
   canary hpc run --backend=slurm ./tests

   # Inspect the batch log after submission
   canary hpc log BATCH_ID

If you already use the legacy batch flags, they still work, but the ``canary
hpc`` commands are the clearer interface going forward.

How It Compares to canary_flux
------------------------------

Use ``canary_hpc`` when you want batching.

- It groups multiple jobs into scheduler submissions.
- It is a good fit for large suites where queue overhead matters.
- It works across multiple backend types, not just Flux.

Use ``canary_flux`` when you want direct Flux execution without a batching
layer.

- Each Canary job is submitted individually inside one Flux allocation.
- It is a better fit when you want Flux-specific behavior and per-job control.

Resource Behavior
-----------------

In HPC mode, resource behavior differs from a normal local run in a few
important ways:

- Resource pool override flags such as ``-r``, ``--resource-pool-file``, and
  ``--oversubscribe`` are rejected.
- The backend defines the available resources.
- Batch-local execution uses the allocation granted by the scheduler, not the
  host machine's local resources.

If your first question is "why are my normal local resource overrides ignored?"
this is usually the reason.

Operational Model
-----------------

The scheduler-backed run follows this sequence:

1. Canary collects and filters jobs.
2. ``canary_hpc`` forms batches.
3. The selected backend validates resource feasibility.
4. Batches are submitted to the scheduler.
5. Each batch runs a nested Canary execution in its batch workspace.
6. Results are collected back into the parent workspace.

This nested execution model is the main conceptual difference between local and
scheduler-backed runs.

See Also
--------

- :doc:`commands`: ``canary hpc`` command reference and examples
- :doc:`batch-specification`: How batch grouping is controlled
- :doc:`resources`: How scheduler resources map into Canary resource pools
- :doc:`limitations`: Important constraints and unsupported combinations
