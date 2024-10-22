.. _howto-run-batched:

Run tests in a scheduler
========================

Tests can be run under a workload manager (scheduler) such as Slurm or PBS by adding the following options to :ref:`nvtest run<nvtest-run>`:

.. code-block:: console

  nvtest run [-l batch:(count=N|length=T)] -l batch:runner=RUNNER ...
  nvtest run [-b (count=N|length=T)] -b runner=RUNNER ...

When run in "batch" mode, ``nvtest`` will group tests into "batches" and submit each batch to ``RUNNER``.

.. note::

  ``-b ARG=VAL`` is an alias for ``-l batch:ARG=VAL``

Batching options
----------------

Batch size
..........

* ``-l batch:count=N``: group tests into ``N`` batches, each having approximately the same runtime.
* ``-l batch:length=T``: group tests into batches having runtime approximately equal to ``T`` seconds.  Accepts Go's duration format eg ``1s``, ``1h``, ``4h30m30s``, etc, are accepted.

By default, tests are batched into groups based as follows:

1. group cases by the number of compute nodes required to run; and
2. partition each group into batches that complete in the time specified by ``-l batch:length=T``.  A default length of 30 minutes is used if not otherwise specified.

.. note::

   ``-l batch:count=N`` and ``-l batch:length=T`` are mutually exclusive.

Batch runner
............

* ``-l batch:runner=S``: use runner ``S`` to run batches.
* ``-l batch:args=S``: pass args ``S`` directly to the runner.  Eg, ``-l batch:args=--account=XYZ`` will pass ``--account=XYZ`` directly to the runner.

The following runners are supported:

* shell (run batches in subprocess of the current shell)
* `slurm workload manager <https://slurm.schedmd.com/overview.html>`_

.. note::

  The shell runner is not performant and its primary utility is running examples on machines which don't have an actual batch runner setup.

Batch concurrency
.................

Batch concurrency can be controlled by

* ``-l session:workers=N``: Submit ``N`` concurrent batches to the runner at any one time.  The default is 5.
* ``-l batch:workers=N``: Execute the batch asynchronously using a pool of at most ``N`` workers.  By default, the maximum number of available workers is used.

Examples
--------

* Run the nvtest example suite in 4 batches

  .. command-output:: nvtest run -d TestResults.Batched -l session:workers=1 -l batch:runner=shell -l batch:count=4 .
    :cwd: /examples
    :extraargs: -rv -w
    :returncode: 30


* Run the nvtest example suite in 4 batches, running tests in serial in each batch

  .. command-output:: nvtest run -d TestResults.Batched -l session:workers=1 -l batch:runner=shell -l batch:count=4 -l batch:workers=1 .
    :cwd: /examples
    :extraargs: -rv -w
    :returncode: 30
