.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Limitations and Constraints
============================

The ``canary_flux`` extension has several important limitations and constraints.

Backend Requirements
====================

Flux Backend Dependency
-----------------------
The Flux extension requires hpc_connect with Flux backend configured.

Resource Pool Constraints
=========================
Resource pool overrides (--resource-pool-file, --oversubscribe) are rejected.

Execution Constraints
=====================
No batching - each job runs individually within single allocation.

Timeout Constraints
===================
Queue, allocation, session, and job timeouts can all affect execution.

Resource Constraints
====================
GPU/CPU assignment depends on Flux environment variables being set correctly.

Debugging Constraints
=====================
Debug mode disables live reporting and may affect execution behavior.

Comparison with HPC Extension
==============================
Flux extension provides direct execution while HPC extension provides batching.
