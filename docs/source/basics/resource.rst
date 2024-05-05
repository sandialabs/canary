.. _nvtest-resource:

Machine resources
=================

``nvtest`` uses the `ProcessPoolExecutor <https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ProcessPoolExecutor>`_ to execute tests asynchronously using :ref:`N <workers>`.  Tests requiring ``np`` processors and ``nd`` devices are submitted to the executor such that the total number of resources used remains less than or equal to the number of available resources.

.. _workers:

Setting the number of workers
-----------------------------

The number of workers ``N`` be specified by the ``-l session:workers:N`` option to ``nvtest run``.  If the number of workers is not given, it will receive a default value based on the following:

* 5 for :ref:`batched <howto-run-batched>` test sessions,
* the number of processors on the machine, otherwise.

Setting the number available processors
---------------------------------------

The number of available processors is found through a system probe [#]_.  The number of available processors can be set with the following :ref:`configuration variables<config-settings>`:

* ``machine:cpu_count``
* the product of ``machine:sockets_per_node`` and ``machine::cores_per_socket``

Setting the number available devices
------------------------------------

The number of available devices is defaults to zero.  The number of available devices can be set with the following :ref:`configuration variables<config-settings>`:

* ``machine:device_count``
* the product of ``machine:sockets_per_node`` and ``machine::devices_per_socket``


.. [#] If `sinfo <https://slurm.schedmd.com/sinfo.html>`_ is detected, it will be used to query the number of available processors on the Slurm nodes.
