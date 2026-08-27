.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_hpc_extension:

Running tests via an HPC batch scheduler
========================================

``canary`` can run tests through a batch scheduler on HPC systems. This mode is designed for running many tests efficiently under queued resource allocation.

Features
--------

* **Bin packing**: tests are packed into batches that are submitted to the scheduler asynchronously.
* **Throughput**: tests within a batch can run concurrently, improving resource utilization and reducing overall time-to-results.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   usage.hpc.run
   usage.hpc.resources
