``ResourcePool``
----------------

A model of the machine

.. revealjs-fragments::

   * Resource *types*: ``cpus``, ``gpus``, ``nodes``, …
   * Resource *instances* with **slots** (capacity)
   * Automatic discovery + manual configuration:

     .. code-block:: yaml

       resource_pool:
         resources:
           cpus:
            - {id: "0", slots: 1}
            - {id: "1", slots: 1}
            - {id: "2", slots: 1}
            - {id: "3", slots: 1}
           gpus:
            - {id: "0", slots: 1}
            - {id: "1", slots: 1}
