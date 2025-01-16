.. _tutorial-parameterize-special:

Special parameter names
=======================

The ``cpus`` and ``gpus`` parameters are :ref:`"resource consuming" <tutorial-resource-pool>` and iterpreted by ``canary`` to be the number of CPUs and GPUs, respectively, needed by the test case.

For example, the test defining parameters

.. code-block:: python

    import canary
    canary.directives.parameterize("cpus,gpus", [(1, 1), (2, 2), (4, 4)])

would generate 3 test cases needing 1, 2, and 4 ``cpus`` and ``gpus``, respectively.

.. admonition:: vvtest compatiblity

    The ``np`` and ``ndevice`` parameters are taken to be synonyms for ``cpus`` and ``gpus``, respectively.

Resource consuming parameters
-----------------------------

More generally, **any** parameter name that appears in the :ref:`resource_pool <tutorial-resource-pool>` are interpreted to be resource consuming.  If the resource is not defined in the :class:`~_canary.config.ResourcePool`, the test will not run due to an unsatisfiable resource constraint.
