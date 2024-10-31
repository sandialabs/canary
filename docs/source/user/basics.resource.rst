.. _basics-resource:

Machine resources
=================

``nvtest`` uses a `ProcessPoolExecutor <https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ProcessPoolExecutor>`_ to execute tests asynchronously using :ref:`N <workers>` workers.  Tests requiring ``np`` processors and ``ngpu`` gpus are submitted to the executor such that the total number of resources used remains less than or equal to the number of available resources.  The availability of resources can be set in one of two ways:

* as a machine configuration setting; and
* as a test session resource limit.

Setting available machine resources
-----------------------------------

The following machine resources can be set in the :ref:`global or local configuration file<configuration>` or from the command line using the ``-c machine:<resource>:<value>`` flag:

* ``cpus_per_node``: the number of CPUs per node available to this test session
* ``gpus_per_node``: the number of GPUs per node available to this test session
* ``node_count``: the number of compute modes available to this test session

Finer-grained control over machine resources can be set via the following variables:

By default, ``nvtest`` performs a system probe [1]_ to determine appropriate values for each machine configuration variable.

.. note::

    ``nvtest`` does not do a system probe to determine the number of GPUs.  The number of available GPUs must be explicitly set.

Setting resources available to a test session
---------------------------------------------

The number of resources made available to a test session can be limited by passing ``-l session:<resource>=<value>`` to :ref:`nvtest run<nvtest-run>`.  Recognized resources are:

* ``cpu_count``: the number of CPUs available to this session.
* ``cpu_ids``: comma-separate list of CPU IDs available to this session.
* ``gpu_count``: the number of GPUs available to this session.
* ``gpu_ids``: comma-separate list of GPU IDs available to this session.
* ``node_count``: the number of compute nodes available to this session.
* ``workers``: the number of simultaneous tests or batches to run.
* ``timeout``: the time, in seconds, the test session can run.  Also accepts GO's time format.

.. note::

    ``cpu_count`` and ``cpu_ids`` are mutually exclusive.  Likewise, ``gpu_count`` and ``gpu_ids`` are mutually exclusive.

.. _workers:

Setting the number of workers
.............................

If the number of workers is not given, it will receive a default value based on the following:

* 5 for :ref:`batched <howto-run-batched>` test sessions,
* the number of processors on the machine, otherwise.

Setting resources available to individual tests
-----------------------------------------------

The number of resources made available to individual tests can be limited by passing ``-l test:<resource>=<value>`` to :ref:`nvtest run<nvtest-run>`.  Recognized resources are:

* ``cpu_count``: ``[min:]max`` CPUs available per test.  Tests requiring less than ``min`` CPUs (default: 1) and tests requiring more than ``max`` CPUs are ignored.
* ``gpu_count``: ``[min:]max`` GPUs available per test.  Tests requiring less than ``min`` GPUs (default: 0) and tests requiring more than ``max`` GPUs are ignored.
* ``node_count``: ``[min:]max`` Compute nodes available per test.  Tests requiring less than ``min`` nodes (default: 1) and tests requiring more than ``max`` nodes are ignored.
* ``timeout``: the time, in seconds, the test can run.  Tests requiring more than ``timeout`` seconds are ignored.  Also accepts GO's time format.
* ``timeoutx``: apply this multiplier to the test's default timeout.

Setting the number of processors required by a test
...................................................

The number of processors required by a test is inferred from the :ref:`np<np-ngpu-parameters>` parameter.  If ``np`` is not set, the number of processors required by the test is assumed to by ``1``.

Setting the number of gpus required by a test
.............................................

The number of gpus required by a test is inferred from the :ref:`ngpu<np-ngpu-parameters>` parameter.  If ``ngpu`` is not set, the number of gpus required by the test is assumed to by ``0``.


CPU and GPU ID identification
------------------------------

When a test is executed by ``nvtest``, it first expands environment variables looking for the placeholders ``%(gpu_ids)s`` and ``%(cpu_ids)s``. It inserts the GPU and CPU IDs [2]_, respectively, into these environment variables. This allows tests to know which CPUs and GPUs it has been allocated.

-----------------------

Examples
--------

* Set the number of CPUs in a configuation file:

  .. code-block:: console

      $ cat ./nvtest.cfg
      [machine]
      cpus_per_node = 32

* Run tests on a machine having 32 processors and 4 gpus:

  .. code-block:: console

      nvtest -c machine:cpus_per_node:32 -c machine:gpus_per_node:4 run ...


* Limit the number of processors used by the test session to 12

  .. code-block:: console

      nvtest -c machine:cpus_per_node:32 -c machine:gpus_per_node:4 run -l session:cpu_count:12 ...

* Set ``CUDA_VISIBLE_DEVICES`` to the GPUs available to a test:

  .. code-block:: console

      export CUDA_VISIBLE_DEVICES="%(gpu_ids)s"
      nvtest -c machine:gpus_per_node:4 run ...

  When each test is launched, ``nvtest`` will replace ``%(gpu_ids)s`` with a comma separated list of the actual GPU IDs allocated to the test.

-----------------------

.. [1] If `sinfo <https://slurm.schedmd.com/sinfo.html>`_ is detected, it will be used to query the number of available processors on the Slurm nodes.
.. [2] The GPU and CPU IDs are ``nvtest``'s internal IDs (number ``0..N-1``) and may not represent actual hardware IDs.
