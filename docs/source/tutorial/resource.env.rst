.. _tutorial-resource-env:

Environment variables
=====================

When a test is executed by ``nvtest`` it sets and passes the following environment variables to the test process:

* ``NVTEST_<NAME>_IDS``: comma separated list of :ref:`global <id-map>` ids for machine resource ``NAME``.

For example, if the following test:

.. code-block:: python

    import nvtest

    nvtest.directives.parameterize("cpus,gpus", ((4, 4)))


acquires CPUs 10, 11, 12, and 13, and GPUs 0, 1, 2, and 3 from the resource pool, respectively, the test environment would have the following variables defined:

* ``NVTEST_CPU_IDS=10,11,12,13``
* ``NVTEST_GPU_IDS=0,1,2,3``

Other environment variables
---------------------------

Existing environment variables having the placeholders ``%(<name>_ids)s`` have those placeholders replaced when the test is run.  If, in the previous example, the environment had defined ``CUDA_VISIBLE_DEVICES="%(gpu_ids)s"``, then ``CUDA_VISIBLE_DEVICES=0,1,2,3`` would be defined in the test environment.
