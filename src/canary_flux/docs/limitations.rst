.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Limitations and Constraints
===========================

``canary_flux`` works well when you want direct Flux execution, but there are a
few important constraints to keep in mind.

Backend Requirements
--------------------

- A working Flux backend through ``hpc_connect`` is required.
- Scheduler-specific behavior is provided by that backend, not by Canary.

Resource Pool Overrides
-----------------------

The normal local resource pool override flags are rejected in Flux mode:

- ``-r``
- ``--resource-pool-file``
- ``--oversubscribe``

In practice, that means resource availability comes from the Flux backend and
the allocation it grants.

No Batching Layer
-----------------

``canary_flux`` does not batch jobs.

- Each selected Canary job is submitted individually.
- All jobs run within the lifetime of a single outer allocation.

If you need batching policy, use ``canary hpc run --backend=flux`` instead.

Timeout Behavior
----------------

Several timeout layers can affect a run:

- queue timeout while waiting for allocation or job start
- allocation timeout for the outer Flux allocation
- session and per-job timeouts inside Canary

If a run stops earlier than expected, check all of those layers.

Environment-Dependent Resource Assignment
-----------------------------------------

GPU and CPU assignment depends on the Flux environment presented to the job.
If the relevant environment variables are missing or incomplete, resource
mapping may not match what you expected.

Debug Mode Tradeoff
-------------------

Debug mode disables live reporting and can change what you see during the run.
Use it when you need more diagnostics, but expect a less polished interactive
display.

See Also
--------

- :doc:`overview`: Direct Flux execution model
- :doc:`commands`: ``canary flux`` command reference
- :doc:`resource-management`: Resource pool and assignment details
- :doc:`/extensions/exts/canary_hpc/index`: Batch-oriented Flux execution via ``canary_hpc``
