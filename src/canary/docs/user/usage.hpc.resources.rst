.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_hpc-resources:

Resource Pool Considerations
============================

When using the ``canary_hpc`` plugin in batched mode, the resource pool is constructed
automatically from the batch scheduler backend (via ``hpc_connect``).  Any resource pool
configuration supplied by the user — whether via command-line arguments, configuration files, or
environment variables — is **rejected** when the HPC plugin is active.  The following options in
particular are not honoured in batch mode:

* ``-r`` / ``--resource-pool-file``
* ``--oversubscribe``
* ``resource_pool:`` configuration keys

.. note::

   Users who need control over the resource pool in HPC mode should configure it through
   ``hpc_connect``.  The resource pool that will be used for a given allocation can be inspected
   with ``canary hpc info`` before submitting.

For each batch job, ``canary`` constructs a per-batch resource pool based on the scheduler's
reported node count and per-node resource topology.  GPU resources discovered through ``hpc_connect``
are given a ``vendor: UNKNOWN`` property to allow vendor-agnostic allocation within batch scripts.

