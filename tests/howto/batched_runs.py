"""

How to run tests in a scheduler
===============================

Tests can be run under a workload manager (scheduler) such as Slurm or PBS. Adding the following options to ``nvtest run``

.. code-block:: console

  nvtest run -l (batch:count:N|batch:time:T) --scheduler SCHEDULER ...

will cause tests to be grouped into "batches" and be submitted to ``SCHEDULER``.

Batching options
----------------

* ``-l batch:count:N``: group tests into ``N`` batches, each having
  approximately the same runtime.

* ``-l batch:time:T``: group tests into batches having runtime approximately
  equal to ``T`` seconds.  Human readable times, eg 1s, 1 sec, 1h, 2 hrs, etc,
  are accepted.
* ``-l session:workers:N``: Submit ``N`` concurrent batches to the scheduler at any
  one time.  The default is 5.

Scheduler options
-----------------

Send options directly to the scheduler via ``-S,option``.  Eg, ``-S,--account=XYZ`` will
pass ``--account=XYZ`` directly to the scheduler.

Supported schedulers
--------------------

At this time, only the ``slurm`` scheduler is supported.

"""


def test_howto_scheduler():
    ...
