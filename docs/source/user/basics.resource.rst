.. _basics-resource:

Resource allocation
===================

``canary`` uses a `ProcessPoolExecutor <https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ProcessPoolExecutor>`_ to execute tests asynchronously using ``N`` workers\ [1]_.  Tests are submitted to the executor such that the number of occupied slots of a resource remains less than or equal to the total number slots available.  Resources across compute nodes are specified within a "resource pool" using a structured JSON format\ [2]_.

Resource pool specification
---------------------------

The resource pool is defined by the ``resource_pool`` :ref:`configuration <configuration>` field.  ``resource_pool`` is an array whose entries are objects representing the resources available on a specific node in your computational environment.  For a desktop or single node-system, the length of the ``resource_pool`` array is ``1``.  For multi-node systems, the ``resource_pool`` will contain one entry per node.  For example, a machine having a single node with ``N-1`` CPUs is defined by:

.. code-block:: json

   {
     "resource_pool": [
       {
         "id": "0",
         "cpus": [
           {
             "id": "0",
             "slots": 1
           },
           {
             "id": "1",
             "slots": 1
           },
           // Repeat entries until "id": "N-1" for N CPUs in total
         ]
       }
     ]
   }

Each entry in the ``resource_pool`` array is a JSON object describing that node's resources.  The object's members are:

* ``id``: a string uniquely identifying the node; and
* arrays describing each named resource type.

On a single node, each resource type is defined by an array of JSON objects whose entries describe a single instance of the specified resource.  Each instance's members are:

* ``id``: a string uniquely identifying this instance of the resource; and
* ``slots``: the number of ``slots`` of the resource available.  If not defined, the number of ``slots`` is 1.

Example
~~~~~~~

A machine having 4 CPUs with one slot each and 2 GPUs with 2 slots each would be defined as:

.. code-block:: json

  {
    "resource_pool": [
      {
        "id": "0",
        "cpus": [
          {"id": "0", "slots": 1},
          {"id": "1", "slots": 1},
          {"id": "2", "slots": 1},
          {"id": "3", "slots": 1}
        ],
        "gpus": [
          {"id": "0", "slots": 2},
          {"id": "1", "slots": 2}
        ]
      }
    ]
  }

Defining the resource pool
--------------------------

By default, the resource pool is automatically generated based on a machine probe and consistes of a single node with ``N`` CPUs *and* 0 GPUs.  The number of CPUs ``N`` is determined by a system probe\ [3]_.  No other resource types are assumed to exist.  Users have the flexibility to define the resource pool in a variety of ways using command line flags, configuration file, or a combination of both, depending on the specific requirements of their computing environment.

.. note::

  * Any resources other than ``cpus`` and ``gpus`` must be defined by the user.
  * ``canary`` assumes a default GPU count of 0

Homogeneous single-node compute environments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For desktop and single-node *homogeneous* compute environments, the resource pool can be specified on the command line by simply defining the number of each resource type.  For example, resource pool having the default CPU count (as determined by ``canary``) and 4 GPUs, can be generated via

.. code-block:: console

  canary -c resource_pool:gpus:4 ...

The resource pool can also be defined in the ``resource_pool`` section of the configuration file:

.. code-block:: yaml

  resource_pool:
    gpus: 4

Homogeneous multi-node compute environments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For homogeneous multi-node compute environments, the resource pool can be specified on the command line by defining the number nodes, and the count per node of each resource type.  For example, resource pool having 4 compute nodes with 32 CPUs and 4 GPUs per node, respectively, can be generated via:

.. code-block:: console

  canary -c resource_pool:nodes=4 -c resource_pool:cpus_per_node=32 -c resource_pool:gpus_per_node=4 ...

The resource pool can also be defined in the ``resource_pool`` section of the configuration file:

.. code-block:: yaml

  resource_pool:
    nodes: 4
    cpus_per_node: 32
    gpus_per_node: 4

.. note::

  On HPC systems, :ref:`hpc-connect` will probe the specified batch scheduler to generate the homogenous multi-node resource pool.

Heterogeneous compute environments
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

Defining resources required by a test case
------------------------------------------

The resources required by a test case are inferred by comparing the case's :ref:`parameters <usage-parameterize>` with the resource types defined in the resource pool.  For example, a test requiring 4 ``cpus`` and 4 ``gpus`` must define the appropriate ``cpus`` and ``gpus`` parameters and the resource pool must contain enough slots of ``cpus`` and ``gpus`` resource types:

.. code-block:: python

  canary.directives.parameterize("cpus,gpus", [(4, 4)])


.. code-block:: yaml

  resource_pool:
    cpus: 32
    gpus: 4

.. note::

  A test case is assumed to require 1 CPU if not otherwise specified by the ``cpus`` parameter.

If a test requires a non-default resource, that resource type must appear in the resource pool - even if the count is 0.  For example, consider the test requiring ``n`` `fpgas <https://en.wikipedia.org/wiki/Field-programmable_gate_array>`_

.. code-block:: python

  canary.directives.parameterize("fpgas", [n])

``canary`` will not treat ``fpgas`` as a resource consuming parameter unless it is explicitly defined within the resource pool - either by the command line, a configuration file, or both. Even if the system does not contain any ``fpgas`` (i.e., the count is 0), the user still must explicitly set the count to zero. Otherwise, ``canary`` will treat ``fpgas`` as a regular parameter and proceed with executing the test on systems not having ``fpgas``.

Environment variables
---------------------

When a test is executed by ``canary`` it sets and passes the following environment variables to the test process:

* ``CANARY_<NAME>_IDS``: comma separated list of :ref:`global <id-map>` ids for machine resource ``NAME``.

For example, consider the test requiring 4 CPUs and 4 GPUs and suppose that ``canary`` acquires CPUs 10, 11, 12, and 13, and GPUs 0, 1, 2, and 3 from the resource pool, respectively. The test environment would have the following variables defined: ``CANARY_CPU_IDS=10,11,12,13`` and ``CANARY_GPU_IDS=0,1,2,3``.

Additionally, existing environment variables having the placeholders ``%(<name>_ids)s`` are replaced with the actual global ids.  If, in the previous example, the session environment had defined ``CUDA_VISIBLE_DEVICES="%(gpu_ids)s"``, then ``CUDA_VISIBLE_DEVICES=0,1,2,3`` would be defined in the test environment.

.. _id-map:

Mapping of global to local resource type IDs
--------------------------------------------

The IDs contained in the resource pool are considered local (to the node) IDs.  ``canary`` maintains a mapping from (node ID, local resource type ID) to an associated global ID.

-----------------------

.. [1] The number of workers can be set by the ``--workers=N`` ``canary run`` flag.
.. [2] ``canary``\ 's resource pool specification is a generalization of `ctest's <https://cmake.org/cmake/help/latest/manual/ctest.1.html#resource-allocation>`_.
.. [3] The CPU IDs are ``canary``'s internal IDs (number ``0..N-1``) and may not represent actual hardware IDs.
