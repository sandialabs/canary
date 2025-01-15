.. _tutorial-batch:

Batched execution
=================

``canary`` supports running tests in "batched" mode. In batched mode:

* tests are grouped into batches;
* batches are submitted to ``hpc_connect`` for submissions to a batch scheduler, such as Slurm or Flux.

.. toctree::
    :maxdepth: 1

    batch.basic
    batch.args
    batch.scheme
