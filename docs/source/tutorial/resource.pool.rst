.. _tutorial-resource-pool:

The resource pool
-----------------

Resources are defined in the ``resource_pool`` :ref:`configuration <configuration>` field.  ``resource_pool`` is:

* an array whose entries are objects representing the resources available on a specific node in your computational environment; and
* sized to contain one entry per node.

For example, a machine having a single node with ``N`` CPUs is defined by:

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
           // ...
           {
             "id": "N-1",
             "slots": 1
           }
         ]
       }
     ]
   }
