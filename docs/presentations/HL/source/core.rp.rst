``ResourcePool``
----------------

A model of machine resources

.. revealjs-fragments::

   * Resource **types** and **capacities** (e.g., CPUs, GPUs)
   * **auto-discovery**, with optional **manual overrides**:

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
