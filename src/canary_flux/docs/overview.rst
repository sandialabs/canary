.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Flux Extension Overview
=======================

``canary_flux`` lets Canary run jobs directly inside a Flux allocation. Use it
when you want Flux-specific execution without the extra batching layer used by
``canary_hpc``.

What It Does
------------

``canary_flux`` keeps Canary's normal collection, selection, dependency, and
resource model, but changes how execution happens:

- Canary asks the Flux backend for an allocation.
- Inside that allocation, each selected Canary job is submitted as its own Flux
  job.
- Canary records timing, environment, and resource metadata for those Flux
  jobs.

This is a good fit when you want direct Flux behavior, per-job submission, and
detailed timing information for the allocation and job lifecycle.

What It Does Not Change
-----------------------

``canary_flux`` does not define job file formats or replace Canary's job
generators. You still describe jobs with ``canary_pyt``, ``canary_vvtest``,
``canary_cmake``, or another generator.

It also does not use batching. If you want Canary to pack many jobs into fewer
scheduler submissions, use ``canary_hpc`` instead.

First Commands
--------------

.. code-block:: console

   # Run tests through a Flux allocation
   canary flux run ./tests

   # Request a larger allocation
   canary flux run --nodes 4 ./tests

   # Pass allocation arguments through to Flux
   canary flux run --alloc-arg="--time-limit=60" ./tests

How It Compares to canary_hpc
-----------------------------

Use ``canary_flux`` when you want direct Flux execution.

- Each Canary job becomes an individual Flux job.
- There is no batching layer.
- Timing and environment capture are more closely tied to the Flux lifecycle.

Use ``canary_hpc`` when you want batch-oriented submission.

- It groups jobs into scheduler batches before execution.
- It works across multiple backend types.
- It is usually the better fit for large suites where batching policy matters.

Resource Behavior
-----------------

In Flux mode, Canary builds its resource pool from the Flux backend and from the
active allocation.

- Resource pool override flags such as ``-r``, ``--resource-pool-file``, and
  ``--oversubscribe`` are rejected.
- Resource counts come from the Flux backend.
- GPU and CPU assignments are derived from the Flux execution environment.

Operational Model
-----------------

The direct Flux workflow looks like this:

1. Canary collects and filters jobs.
2. ``canary_flux`` requests a Flux allocation.
3. Once the allocation is active, Canary submits each selected job inside it.
4. Each job runs through ``canary flux exec``.
5. Canary records results, timing, and debug metadata.

This model keeps scheduling visible at the job level instead of hiding it behind
batches.

See Also
--------

- :doc:`commands`: ``canary flux`` command reference and examples
- :doc:`resource-management`: How allocations map into Canary resource pools
- :doc:`timing-metrics`: Timing fields recorded for Flux runs
- :doc:`limitations`: Important constraints of the direct Flux workflow
