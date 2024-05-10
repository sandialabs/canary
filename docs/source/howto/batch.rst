.. _howto-run-batched:

Run tests in a scheduler
========================

Tests can be run under a workload manager (scheduler) such as Slurm or PBS by adding the following options to :ref:`nvtest run<nvtest-run>`:

.. code-block:: console

  nvtest run [-b (count:N|length:T)] -b scheduler:SCHEDULER ...

When run in "batch" mode, ``nvtest`` will group tests into "batches" and submit each batch to ``SCHEDULER``.

Batching options
----------------

Batch size
..........

* ``-b count:N``: group tests into ``N`` batches, each having approximately the same runtime.
* ``-b length:T``: group tests into batches having runtime approximately equal to ``T`` seconds.  Human readable times, eg 1s, 1 sec, 1h, 2 hrs, etc, are accepted.
* ``-b workers:N``: Run tests in this batch asynchronously with at most ``N`` workers.

By default, tests are batched into groups based as follows:

1. group cases by the number of compute nodes required to run; and
2. partition each group into batches that complete in the time specified by ``-b length:T``.  A default length of 30 minutes is used if not otherwise specified.

.. note::

   ``-b count:N`` and ``-b length:T`` are mutually exclusive.

Batch scheduler
................

* ``-b scheduler:S``: use scheduler ``S`` to run batches.
* ``-b args:S``: pass args ``S`` directly to the scheduler.  Eg, ``-b args:--account=XYZ`` will pass ``--account=XYZ`` directly to the scheduler.

The following schedulers are supported:

* shell (run batches in subprocess of the current shell)
* `slurm workload manager <https://slurm.schedmd.com/overview.html>`_

.. note::

  The shell scheduler is not performant and its primary utility is running examples on machines which don't have an actual scheduler setup.

Batch concurrency
.................

Batch concurrency can be controlled by

* ``-l session:workers:N``: Submit ``N`` concurrent batches to the scheduler at any one time.  The default is 5.
* ``-b workers:N``: Execute the batch asynchronously using a pool of at most ``N`` workers.  By default, the maximum number of available workers is used.

Examples
--------

* Run the nvtest example suite in 4 batches

  .. command-output:: nvtest run -d TestResults.Batched -b scheduler:shell -b count:4 .
    :cwd: /examples
    :extraargs: -rv -w
    :returncode: 30


* Run the nvtest example suite in 4 batches, running tests in serial in each batch

  .. command-output:: nvtest run -d TestResults.Batched -b scheduler:shell -b count:4 -b workers:1 .
    :cwd: /examples
    :extraargs: -rv -w
    :returncode: 30
