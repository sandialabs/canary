.. _basics-resource:

Machine resources
=================

``nvtest`` uses the `ProcessPoolExecutor <https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ProcessPoolExecutor>`_ to execute tests asynchronously using :ref:`N <workers>` workers.  Tests requiring ``np`` processors and ``ngpu`` gpus are submitted to the executor such that the total number of resources used remains less than or equal to the number of available resources.

.. _workers:

Setting the number of workers
-----------------------------

The number of workers ``N`` be specified by the ``-l session:workers=N`` option to ``nvtest run``.  If the number of workers is not given, it will receive a default value based on the following:

* 5 for :ref:`batched <howto-run-batched>` test sessions,
* the number of processors on the machine, otherwise.

Setting the number available processors
---------------------------------------

The number of available processors is found through a system probe [#]_.  The number of available processors can be set with the following :ref:`configuration variables<configuration>`:

* ``machine:cpu_count``
* the product of ``machine:sockets_per_node`` and ``machine:cores_per_socket``

The number of processors used by a test session can be limited by setting the ``-l session:cpu_count=N`` option to :ref:`nvtest run <nvtest-run>`.

Setting the number of processors required by a test
---------------------------------------------------

The number of processors required by a test is inferred from the :ref:`np<np-ngpu-parameters>` parameter.  If ``np`` is not set, the number of processors required by the test is assumed to by ``1``.

Setting the number available gpus
---------------------------------

The number of available gpus defaults to zero.  The number of available gpus can be set with the following :ref:`configuration variables<configuration>`:

* ``machine:gpu_count``
* the product of ``machine:sockets_per_node`` and ``machine:gpus_per_socket``

The number of gpus used by a test session can be limited by setting the ``-l session:gpu_count=N`` option to :ref:`nvtest run <nvtest-run>`.

Setting the number of gpus required by a test
---------------------------------------------

The number of gpus required by a test is inferred from the :ref:`ngpu<np-ngpu-parameters>` parameter.  If ``ngpu`` is not set, the number of gpus required by the test is assumed to by ``0``.

.. [#] If `sinfo <https://slurm.schedmd.com/sinfo.html>`_ is detected, it will be used to query the number of available processors on the Slurm nodes.
