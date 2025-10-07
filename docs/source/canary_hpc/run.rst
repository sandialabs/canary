.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_hpc-run:

Running tests in a scheduler
============================

Tests can be run under a workload manager (scheduler) such as Slurm or PBS by adding the following options to :ref:`canary run<canary-run>`:

.. code-block:: console

  canary run [-b spec=(duration:T|count:{max,auto,N})[,layout:{flat,atomic}][,nodes:{any,same}]] -b scheduler=SCHEDULER -b workers=N ...

When run in "batch" mode, ``canary`` will group tests into "batches" and submit each batch to ``SCHEDULER``.

Batching options
----------------

Batch spec
..........

* if ``duration:T``: create batches with approximate run length of ``T`` seconds
* if ``count:max``: one test per batch
* if ``count:auto``: auto batch depending on other options
* if ``count:N``: create at most ``N`` batches

* if ``layout:flat``: batches have no intra-batch dependencies but may have inter-batch dependencies
* if ``layout:atomic``: batch have no inter-batch dependencies but may have intra-batch dependencies

* if ``nodes:any``: tests are batched with respect to node count of test cases
* if ``nodes:same``: tests are batched with tests having the same node count

The default batch spec is ``duration:30m,nodes:any,layout:flat``.

.. note::

   ``-b spec=count:N`` and ``-b spec=duration:T`` are mutually exclusive.

Batch scheduler
...............

* ``-b scheduler=S``: use scheduler ``S`` to run batches.
* ``-b option=option``: pass *option* to the scheduler. If *option* contains commas, it is split into multiple options at the commas.  Eg, ``-b option="-q debug,-A ABC123"`` passes ``-q debug`` and ``-ABC123`` directly to the scheduler.

The following schedulers are currently supported:

* shell (run batches in subprocess of the current shell)
* `slurm <https://slurm.schedmd.com/overview.html>`_
* `flux <https://flux-framework.readthedocs.io>`_
* PBS

.. note::

  The shell scheduler is not performant and its primary utility is running examples on machines which don't have an actual batch scheduler setup.

Batch concurrency
.................

Batch concurrency can be controlled by

* ``--workers=N``: Submit ``N`` concurrent batches to the scheduler at any one time.  The default is 5.
* ``-b workers=N``: Execute the batch asynchronously using a pool of at most ``N`` workers.  By default, the maximum number of available workers is used.

Rerunning tests
---------------

Navigate to the test results directory and execute :ref:`canary run<canary-run>` to rerun tests:

.. code-block:: console

   canary -C TEST_RESULTS_DIR run [OPTIONS]


or

.. code-block:: console

   cd TEST_RESULTS_DIR
   canary run [OPTIONS]

where ``TEST_RESULTS_DIR`` is the test results directory.

When a test session is created in batched mode, the batch arguments from the test session invocation are inherited in future reruns.

Examples
--------

* Run the canary example suite in 4 batches

  .. command-output:: canary run -d TestResults.Batched --workers=1 -b scheduler=shell -b spec=count:4 .
    :cwd: /examples
    :setup: rm -rf TestResults.Batched
    :returncode: 30


* Run the canary example suite in 4 batches, running tests in serial in each batch

  .. command-output:: canary run -d TestResults.Batched --workers=1 -b scheduler=shell -b spec=count:4 -b workers=1 .
    :cwd: /examples
    :setup: rm -rf TestResults.Batched
    :returncode: 30
