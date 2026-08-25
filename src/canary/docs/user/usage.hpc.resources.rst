.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_hpc-resources:

Resource Pool Considerations
============================

When using the ``canary_hpc`` plugin in batched mode, any resource pool configurations defined by the user are disregarded. This applies to configurations specified through command line arguments as well as those set in configuration files. Instead, the resource pool for ``canary`` is automatically populated by the backend of the batch scheduler.

Users wanting control over the resource pool should configure it through ``hpc_connect``.
