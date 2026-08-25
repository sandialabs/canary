.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-batch:

Batched execution
=================

``canary`` can run tests in *batched* mode via the :ref:`canary_hpc_extension` plugin. In batched mode:

* test cases are grouped into batches; and
* each batch is submitted to ``hpc_connect`` for execution under a batch scheduler (for example,
  Slurm, Flux, or PBS).

This is useful when you want the scheduler to manage queueing and node allocation, while ``canary``
continues to manage test discovery, dependencies, and result reporting.

.. toctree::
    :maxdepth: 1

    batch.basic
    batch.spec
    batch.args
