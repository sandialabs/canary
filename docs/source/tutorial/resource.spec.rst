.. _tutorial-resource-spec:

Resource pool spec
==================

Each entry in the ``resource_pool`` array is a JSON object describing that node's resources.  Each object's members are:

* ``id``: a string uniquely identifying the node; and
* arrays describing each named resource type.

On each node, each resource type is defined by an array of JSON objects whose entries describe a single instance of the specified resource.  Each instance's members are:

* ``id``: a string uniquely identifying this instance of the resource; and
* ``slots``: the number of ``slots`` of the resource available.  If not defined, the number of ``slots`` is 1.

Example
-------

A machine having 4 CPUs with one slot each and 2 GPUs with 2 slots each would be defined as:

.. code-block:: json

  {
    "resource_pool": [
      {
        "cpus": [
          {"id": "0", "slots": 1},
          {"id": "1", "slots": 1},
          {"id": "2", "slots": 1},
          {"id": "3", "slots": 1}
        ]
      },
      {
        "gpus": [
          {"id": "0", "slots": 2},
          {"id": "1", "slots": 2}
        ]
      }
    ]
  }
