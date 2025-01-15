.. _tutorial-resource:

Resource allocation
===================

``canary`` uses a `ProcessPoolExecutor <https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ProcessPoolExecutor>`_ to execute tests asynchronously using ``N`` workers\ [1]_.  Tests are submitted to the executor such that the number of occupied slots of a resource remains less than or equal to the total number slots available.  Resources across compute nodes are specified within a "resource pool" using a structured JSON format\ [2]_.

.. toctree::
    :maxdepth: 1

    resource.pool
    resource.defn
    resource.reqd
    resource.env

.. [1] The number of workers can be set by the ``--workers=N`` ``canary run`` flag.
.. [2] ``canary``\ 's resource pool specification is a generalization of `ctest's <https://cmake.org/cmake/help/latest/manual/ctest.1.html#resource-allocation>`_.
