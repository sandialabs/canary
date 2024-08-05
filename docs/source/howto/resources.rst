.. _howto-resources:

Set available resources
=======================

``nvtest`` uses a `ProcessPoolExecutor <https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ProcessPoolExecutor>`_ to execute tests asynchronously using :ref:`N <workers>` workers.  Tests requiring ``np`` processors and ``ngpu`` gpus are submitted to the executor such that the total number of resources used remains less than or equal to the number of available resources.  The availability of resources can be set in one of two ways:

* as a machine configuration setting; and
* as a test session resource limit.

Setting available machine resources
-----------------------------------

The following machine resources can be set in the :ref:`global or local configuration file<introduction-config>` or from the command line:

* ``cpu_count``: the number of CPUs available to this test session
* ``gpu_count``: the number of GPUs available to this test session

Finer-grained control over machine resources can be set via the following variables:

* ``nodes``: the number of compute nodes on the compute cluster
* ``sockets_per_node``: the number of sockets on each compute node
* ``cores_per_socket``: the number of CPU cores on each socket
* ``gpus_per_socket``: the number of GPUs on each socket

If the latter variables are defined, then ``cpu_count`` is set equal to ``nodes * sockets_per_node * cores_per_socket`` and  ``gpu_count = nodes * sockets_per_node * gpus_per_socket``.

By default, ``nvtest`` performs a system probe to determine appropriate values for each machine configuration variable.

.. note::

    ``nvtest`` does not do a system probe to determine the number of GPUs.  The number of available GPUs must be explicitly set.

.. rubric:: Example: set the number of CPUs in a configuation file:

.. code-block:: console

    $ cat ./nvtest.cfg
    [machine]
    cpu_count = 32

.. rubric:: Example: set the number of CPUs on the command line:

.. code-block:: console

    nvtest -c machine:cpu_count:32 ...

Setting resources available to a test session
---------------------------------------------

The number of resources made available to a test session can be limited by passing ``-l session:<resource>=<value>`` to :ref:`nvtest run<nvtest-run>`.  Recognized resources are:

* ``cpu_count``: the number of CPUs available to this session.
* ``cpu_ids``: comma-separate list of CPU IDs available to this session.
* ``gpu_count``: the number of GPUs available to this session.
* ``gpu_ids``: comma-separate list of GPU IDs available to this session.
* ``workers``: the number of simultaneous tests or batches to run.
* ``timeout``: the time, in seconds, the test session can run.  Also accepts GO's time format.

.. note::

    ``cpu_count`` and ``cpu_ids`` are mutually exclusive.  Likewise, ``gpu_count`` and ``gpu_ids`` are mutually exclusive.

Setting resources available to individual tests
-----------------------------------------------

The number of resources made available to individual tests can be limited by passing ``-l test:<resource>=<value>`` to :ref:`nvtest run<nvtest-run>`.  Recognized resources are:

* ``cpus``: ``[min:]max`` CPUs available per test.  Tests requiring less than ``min`` CPUs (default: 0) and tests requiring more than ``max`` CPUs are ignored.
* ``gpus``: GPUs available per test.  Tests requiring more than ``gpus`` GPUs are ignored.
* ``timeout``: the time, in seconds, the test can run.  Tests requiring more than ``timeout`` seconds are ignored.  Also accepts GO's time format.
* ``timeoutx``: apply this multiplier to the test's default timeout.
