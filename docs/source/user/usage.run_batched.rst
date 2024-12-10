.. _usage-run-batched:

Running tests in a scheduler
============================

Tests can be run under a workload manager (scheduler) such as Slurm or PBS by adding the following options to :ref:`nvtest run<nvtest-run>`:

.. code-block:: console

  nvtest run [-b (count=N|length=T)] -b scheduler=SCHEDULER ...

When run in "batch" mode, ``nvtest`` will group tests into "batches" and submit each batch to ``SCHEDULER``.

Batching options
----------------

Batch size
..........

* ``-b count=N``: group tests into ``N`` batches, each having approximately the same runtime.
* ``-b length=T``: group tests into batches having runtime approximately equal to ``T`` seconds.  Accepts Go's duration format eg ``1s``, ``1h``, ``4h30m30s``, etc, are accepted.

By default, tests are batched into groups based as follows:

1. group cases by the number of compute nodes required to run; and
2. partition each group into batches that complete in the time specified by ``-b length=T``.  A default length of 30 minutes is used if not otherwise specified.

.. note::

   ``-b count=N`` and ``-b length=T`` are mutually exclusive.

Batch scheduler
...............

* ``-b scheduler=S``: use scheduler ``S`` to run batches.
* ``-b option=option``: pass *option* to the scheduler. If *option* contains commas, it is split into multiple options at the commas.  Eg, ``-b option="-q debug,-A ABC123"`` passes ``-q debug`` and ``-ABC123`` directly to the scheduler.

The following schedulers are supported:

* shell (run batches in subprocess of the current shell)
* `slurm workload manager <https://slurm.schedmd.com/overview.html>`_

.. note::

  The shell scheduler is not performant and its primary utility is running examples on machines which don't have an actual batch scheduler setup.

Batch concurrency
.................

Batch concurrency can be controlled by

* ``--workers=N``: Submit ``N`` concurrent batches to the scheduler at any one time.  The default is 5.
* ``-b workers=N``: Execute the batch asynchronously using a pool of at most ``N`` workers.  By default, the maximum number of available workers is used.

Examples
--------

* Run the nvtest example suite in 4 batches

  .. command-output:: nvtest run -d TestResults.Batched --workers=1 -b scheduler=shell -b count=4 .
    :cwd: /examples
    :extraargs: -rv -w
    :returncode: 30


* Run the nvtest example suite in 4 batches, running tests in serial in each batch

  .. command-output:: nvtest run -d TestResults.Batched --workers=1 -b scheduler=shell -b count=4 -b workers=1 .
    :cwd: /examples
    :extraargs: -rv -w
    :returncode: 30
