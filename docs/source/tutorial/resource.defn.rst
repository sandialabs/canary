.. _tutorial-resource-defn:

Defining the resource pool
==========================

By default:

* The resource pool is automatically generated based on the :ref:`machine configuration <machine_config>` and consists of a single node with ``N`` CPUs *and* 0 GPUs
* The number of CPUs ``N`` is determined by a system probe\ [3]_
* No other resource types are assumed to exist

Users have the flexibility to define the resource pool in a variety of ways using command line flags, configuration file, or a combination of both, depending on the specific requirements of their computing environment.

.. note::

  * Any resources other than ``cpus`` and ``gpus`` must be defined by the user.
  * ``nvtest`` assumes a default GPU count of 0

Homogeneous single-node compute environments
--------------------------------------------

For desktop and single-node *homogeneous* compute environments, the resource pool can be specified on the command line by simply defining the number of each resource type.  For example, resource pool having the default CPU count (as determined by ``nvtest``) and 4 GPUs, can be generated via

.. code-block:: console

  nvtest -c resource_pool:gpus:4 ...

The resource pool can also be defined in the ``resource_pool`` section of the configuration file:

.. code-block:: yaml

  resource_pool:
    gpus: 4

Homogeneous multi-node compute environments
-------------------------------------------

For homogeneous multi-node compute environments, the resource pool can be specified on the command line by defining the number nodes, and the count per node of each resource type.  For example, resource pool having 4 compute nodes with 32 CPUs and 4 GPUs per node, respectively, can be generated via:

.. code-block:: console

  nvtest -c resource_pool:nodes=4 -c resource_pool:cpus_per_node=32 -c resource_pool:gpus_per_node=4 ...

The resource pool can also be defined in the ``resource_pool`` section of the configuration file:

.. code-block:: yaml

  resource_pool:
    nodes: 4
    cpus_per_node: 32
    gpus_per_node: 4

.. note::

  On HPC systems, :ref:`hpc-connect` will probe the specified batch scheduler to generate the homogenous multi-node resource pool.

Heterogeneous compute environments
----------------------------------

For heterogeneous single or multi-node compute environments, the resource pool must by specified in the ``resource_pool`` section of a configuration file.  The resource pool must define the CPU configuration on each node in addition to any other named resource type.  The resource types *must not* end in ``_per_node``.  For example, a pool having 1 node with ``N`` CPUs with 1 slot per CPU and 4 GPUs with 2, 2, 4, and 4 slots, respectively, would be defined in the configuration file as:

.. code-block:: yaml

  resource_pool:
  - id: "0"
    cpus:
    - id: "0"
      slots: 1
    - id: "1"
      slots: 1
    # Repeat entries until "id": "N-1" for N CPUs in total
    - id: "N-1"
      slots: 1
    gpus:
    - id: "0"
      slots: 2
    - id: "1"
      slots: 2
    - id: "2"
      slots: 4
    - id: "3"
      slots: 4


-----------------------

.. [3] The CPU IDs are ``nvtest``'s internal IDs (number ``0..N-1``) and may not represent actual hardware IDs.
