.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-batch-scheme:

Batching schemes
================

``canary`` supports 3 batching schemes:

* ``-b scheme=duration``: (impled by ``-b duration=T``) group tests into batches such that the duration of each batch is approximately equal to ``T`` seconds.
* ``-b scheme=count``: (implied by ``-b count=N``) group tests into ``N`` batches.
* ``-b scheme=isolate``: group tests such that there are no inter-group dependencies.  Useful for schedulers, like Flux, that support subscheduling.
