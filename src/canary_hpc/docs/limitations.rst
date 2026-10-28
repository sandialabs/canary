.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Limitations
===========

``canary_hpc`` is useful for scheduler-backed execution, but it is not a drop-in
replacement for a local run. The main constraints are below.

Backend Required
----------------

- A working ``hpc_connect`` backend is required.
- Scheduler-specific behavior comes from that backend and from scheduler policy,
  not from Canary alone.

No Local Resource Overrides
---------------------------

In HPC mode, Canary rejects the local resource-pool override flags:

- ``-r``
- ``--resource-pool-file``
- ``--oversubscribe``

Resource availability comes from the selected backend and from the allocation it
creates for each batch.

Batching Rules Matter
---------------------

Not every batch specification is valid.

- ``layout=atomic`` requires ``nodes=any``.
- ``count=auto`` is no longer supported.
- Duration-targeted atomic batching is not supported.
- ``count=N`` still depends on the selected jobs, dependency graph, and
  available resources.

If a run behaves unexpectedly, check the batch specification first.

Nested Execution Changes Debugging
----------------------------------

Each batch runs a nested Canary execution inside its batch workspace.

- Logs and metadata are split between the parent workspace and batch workspaces.
- Debugging is more involved than for a local run.
- A failure may come from batch submission, allocation, nested execution, or the
  job itself.

In practice, ``canary hpc log`` and batch workspace inspection are often part of
normal troubleshooting.

Timeouts Can Stop Runs at Multiple Layers
-----------------------------------------

Queue and run timeouts can both stop work before you get job results.

- Queue timeout can fire before the scheduler starts a batch.
- Run timeout can cancel a batch during execution.
- Scheduler walltime and Canary timeouts need to make sense together.

Use conservative timeout values until you understand scheduler wait time and
batch duration for the target workload.

Large or Mixed Workloads Need Tuning
------------------------------------

Batching is not free.

- Large suites may need batch-spec tuning for good throughput.
- Mixed node counts or mixed resource requirements can reduce packing quality.
- Very small batches can increase scheduler overhead.
- Very large batches can make failures slower to isolate.

This is usually an operational tuning problem, not a correctness problem.

GPU Behavior Depends on the Backend
-----------------------------------

GPU resources are only as specific as the backend makes them.

- Generic HPC mode treats GPU resources through the backend resource model.
- Vendor-specific behavior may require GPU-specific extensions such as
  ``canary_amd`` or ``canary_nvidia``.

See Also
--------

- :doc:`overview`: Scheduler-backed execution model
- :doc:`commands`: ``canary hpc`` command reference
- :doc:`batch-specification`: Batch specification syntax and constraints
- :doc:`debugging`: Troubleshooting scheduler-backed runs
