.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-batch-spec:

Batch specification
===================

Batched execution partitions discovered test cases into one or more *batches* that are submitted
to a scheduler via the ``canary_hpc`` plugin. The batching behavior is controlled by the
``-b spec=SPEC`` option.

Syntax
------

``SPEC`` is a comma-separated list of ``key:value`` or ``key=value`` pairs:

.. code-block:: console

   -b spec=key:value[,key:value...]

Recognized keys
---------------

``count``
  Choose how many batches to create.

  * ``count:N`` where ``N`` is a positive integer: partition into exactly ``N`` batches.
  * ``count:max``: create one batch per test case.

  .. note::

     ``count:auto`` is no longer supported.  Use ``duration:T`` to target a batch runtime instead.

  .. warning::

     ``count:N`` is rejected when ``nodes:same`` is specified and the selected jobs span more than
     one distinct node count.  Each distinct node count forms its own allocation, so a single global
     count cannot be honoured as a hard limit across a heterogeneous mix.  Use ``duration:T``
     instead, or filter the selection to jobs with a single node count:

     .. code-block:: console

        canary run -b scheduler=slurm -b spec=layout=flat,count=4,nodes=same -k 'np==2' PATH

  When distributing a batch count across multiple topological or node-count partitions, the
  leftover budget (from integer-floor division) is awarded to the heaviest partitions first, so
  the dominant independent partition gets the largest share rather than the budget being spread
  thinly across many small partitions.

``duration``
  Target runtime for each batch, used to size batches automatically.

  ``duration`` may be given as:

  * an integer number of seconds (e.g., ``duration:1800``), or
  * Go-style durations (e.g., ``40s``, ``2h``, ``4h30m30s``).

  .. note::

     ``duration`` and ``count`` may not both be set at the same time.

``layout``
  Choose how dependencies are treated *within* a batch.

  * ``layout:flat`` (default): no test case in a batch will depend on another test case in the
    same batch. As a result, batches may depend on other batches.
  * ``layout:atomic``: test cases in the same batch may depend on each other. Batches do not
    depend on other batches.

``nodes``
  Constrain batching with respect to requested node counts.

  * ``nodes:any`` (default): ignore node counts when batching.
  * ``nodes:same``: require all test cases in a batch to request the same node count.

  .. note::

     ``layout:atomic`` is not allowed with ``nodes:same``.

Defaults
--------

If neither ``count`` nor ``duration`` are provided, the default behavior is to target a batch
runtime of 30 minutes:

* ``duration:1800`` (30 minutes)
* ``layout:flat``
* ``nodes:any``

Examples
--------

Partition into batches of roughly 30 minutes (same nodes per batch), with a flat layout:

.. code-block:: console

   canary run -b scheduler=slurm -b spec=layout=flat,nodes=same,duration=1800 PATH

Create exactly two independent batches, allowing dependencies within each batch:

.. code-block:: console

   canary run -b scheduler=slurm -b spec=layout=atomic,count=2 PATH

Create one batch per test case:

.. code-block:: console

   canary run -b scheduler=slurm -b spec=count=max PATH
