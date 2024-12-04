.. _basics-resource:

Resource allocation
===================

``nvtest`` uses a `ProcessPoolExecutor <https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ProcessPoolExecutor>`_ to execute tests asynchronously using :ref:`N <workers>` workers.  Tests are submitted to the executor such that the total number of resources used remains less than or equal to the number of available resources.  The availability of resources is controlled by a :class:`~_nvtest.config.ResourcePool`.  The resource pool is automatically generated based on the :ref:`machine configuration <machine_config>`.

By default, ``nvtest`` performs a system probe [1]_ to determine appropriate values for each machine configuration variable but these variables can be overridden on the command line.  For example, to set the number of nodes and CPUs per node:

.. code-block:: console

  nvtest -c machine:node_count=N -c machine:cpus_per_node=M

New machine resources can also be generated:

.. code-block:: console

  nvtest -c machine:node_count=N -c machine:fgpas_per_node=M

``nvtest`` does not do a system probe to determine the number of GPUs.  The number of available GPUs must be explicitly set.

.. code-block:: console

  nvtest -c machine:node_count=N -c machine:gpus_per_node=M

.. _workers:

Setting the number of workers
.............................

If the number of workers is not given, it will receive a default value based on the following:

* 5 for :ref:`batched <usage-run-batched>` test sessions,
* the number of processors on the machine, otherwise.

Setting the number of processors required by a test
...................................................

The number of processors required by a test is inferred from the :ref:`cpus<cpus-gpus-parameters>` parameter.  If ``cpus`` is not set, the number of processors required by the test is assumed to by ``1``.

Setting the number of gpus required by a test
.............................................

The number of gpus required by a test is inferred from the :ref:`gpus<cpus-gpus-parameters>` parameter.  If ``gpus`` is not set, the number of gpus required by the test is assumed to by ``0``.

Environment variables
---------------------

When a test is executed by ``nvtest`` it sets and passes the following environment variables to the test process:

* ``NVTEST_<NAME>_IDS`` is a comma separated list of **globall** ids for machine resource ``NAME``.

Additionally, existing environment variables having the placeholders ``%(gpu_ids)s`` and ``%(cpu_ids)s`` are expanded with ``gpu_ids`` and ``cpu_ids`` being replaced with their global ids.

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

      nvtest -c machine:node_count -c machine:cpus_per_node:12 run ...

* Set ``CUDA_VISIBLE_DEVICES`` to the GPUs available to a test:

  .. code-block:: console

      export CUDA_VISIBLE_DEVICES="%(gpu_ids)s"
      nvtest -c machine:gpus_per_node:4 run ...

  When each test is launched, ``nvtest`` will replace ``%(gpu_ids)s`` with a comma separated list of the actual GPU IDs allocated to the test.

-----------------------

.. [1] If `sinfo <https://slurm.schedmd.com/sinfo.html>`_ is detected, it will be used to query the number of available processors on the Slurm nodes.
.. [2] The GPU and CPU IDs are ``nvtest``'s internal IDs (number ``0..N-1``) and may not represent actual hardware IDs.
