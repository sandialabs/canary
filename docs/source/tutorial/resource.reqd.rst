.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-resource-reqd:

Defining resources required by a test case
==========================================

The resources required by a test case are inferred by comparing the case's :ref:`parameters <usage-parameterize>` with the resource types defined in the resource pool.

Consider the following test:

.. code-block:: python

  canary.directives.parameterize("cpus,gpus", [(4, 4)])

This test requires 4 ``cpus`` and 4 ``gpus`` and the resource pool must define enough slots of ``cpus`` and ``gpus`` resource types, e.g.:

.. code-block:: yaml

  resource_pool:
    cpus: 32
    gpus: 4

.. note::

  A test case is assumed to require 1 CPU if not otherwise specified by the ``cpus`` parameter.

---------------------

If a test requires a non-default resource, that resource type must appear in the resource pool - even if the count is 0.  For example, consider the test requiring ``n`` `fpgas <https://en.wikipedia.org/wiki/Field-programmable_gate_array>`_

.. code-block:: python

  canary.directives.parameterize("fpgas", [n])

``canary`` will not treat ``fpgas`` as a resource consuming parameter unless it is explicitly defined within the resource pool - either by the command line, a configuration file, or both. Even if the system does not contain any ``fpgas`` (i.e., the count is 0), the user still must explicitly set the count to zero. Otherwise, ``canary`` will treat ``fpgas`` as a regular parameter and proceed with executing the test on systems not having ``fpgas``.
