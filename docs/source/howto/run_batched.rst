.. _howto-run-batched:

How to run tests in a scheduler
===============================

Tests can be run under a workload manager (scheduler) such as Slurm or PBS by adding the following options to ``nvtest run``

.. code-block:: console

  nvtest run [-b (count=N|limit=T)] -b scheduler=SCHEDULER ...

When run in "batch" mode, ``nvtest`` will group tests into "batches" and submit each batch to ``SCHEDULER``.

Batching options
----------------

* ``-b count=N``: group tests into ``N`` batches, each having approximately the same runtime.
* ``-b limit=T``: group tests into batches having runtime approximately equal to ``T`` seconds.  Human readable times, eg 1s, 1 sec, 1h, 2 hrs, etc, are accepted.
* ``-l session:workers=N``: Submit ``N`` concurrent batches to the scheduler at any one time.  The default is 5.
* ``-l batch:workers=N``: Execute the batch asynchronously using a pool of at most ``N`` workers.  By default, the maximum number of available workers is used.

.. note::

   ``-b count=N`` and ``-b limit=T`` are mutually exclusive.

.. note::

   A default of 30 minutes is used if neither the batch time or count is specified.

Scheduler options
-----------------

Send options directly to the scheduler via ``-R,option``.  Eg, ``-R,--account=XYZ`` will
pass ``--account=XYZ`` directly to the scheduler.

Supported schedulers
--------------------

* shell (run batches in subprocess of the current shell)
* `slurm workload manager <https://slurm.schedmd.com/overview.html>`_

.. note::

  The shell scheduler is not performant and its primary utility is running examples on machines which don't have an actual scheduler setup.

Examples
--------

* Run the nvtest example suite in 4 batches

  .. command-output:: nvtest run -d TestResults.Batched -b scheduler=shell -b count=4 .
    :cwd: /examples
    :returncode: 32


* Run the nvtest example suite in 4 batches, running tests in serial in each batch

  .. command-output:: nvtest run -d TestResults.Batched -b scheduler=shell -b count=4 -l batch:workers=1 .
    :cwd: /examples
    :returncode: 32
