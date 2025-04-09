.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-resource-env:

Environment variables
=====================

When a test is executed by ``canary`` it sets and passes the following environment variables to the test process:

* ``CANARY_<NAME>_IDS``: comma separated list of :ref:`global <id-map>` ids for machine resource ``NAME``.

For example, if the following test:

.. code-block:: python

    import canary

    canary.directives.parameterize("cpus,gpus", ((4, 4)))


acquires CPUs 10, 11, 12, and 13, and GPUs 0, 1, 2, and 3 from the resource pool, respectively, the test environment would have the following variables defined:

* ``CANARY_CPU_IDS=10,11,12,13``
* ``CANARY_GPU_IDS=0,1,2,3``

Other environment variables
---------------------------

Existing environment variables having the placeholders ``%(<name>_ids)s`` have those placeholders replaced when the test is run.  If, in the previous example, the environment had defined ``CUDA_VISIBLE_DEVICES="%(gpu_ids)s"``, then ``CUDA_VISIBLE_DEVICES=0,1,2,3`` would be defined in the test environment.

CTest environment variables
---------------------------

For CTest tests, ``canary`` defines environment variables in a manner consistent with `CTest conventions <https://cmake.org/cmake/help/latest/manual/ctest.1.html#environment-variables>`_.
