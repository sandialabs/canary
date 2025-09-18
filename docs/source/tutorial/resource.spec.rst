.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-resource-spec:

Resource Pool Specification
===========================

The ``resource_pool`` is a JSON object describing resources available to ``caanary``. There are two fields in the ``resource_pool`` object: ``additional_properties`` and ``resources``.

Fields:
-------

- **additional_properties**: A JSON object for any extra properties that may be needed.
- **resources**: A collection of available resources, which can include CPUs, GPUs, and other resource types.

Example
-------

A machine having 4 CPUs with one slot each and 2 GPUs with 2 slots each would be defined as:

.. code-block:: yaml

   resource_pool:
     additional_properties: {}
     resources:
       cpus:
       - id: "0"
         slots: 1
       - id: "1"
         slots: 1
       - id: "2"
         slots: 1
       - id: "3"
         slots: 1
       gpus:
       - id: "0"
         slots: 2
       - id: "1"
         slots: 2

Field Descriptions:
--------------------

- **id**:
  - A unique identifier for each resource.
  - Used to reference specific resources in configurations.

- **slots**:
  - The number of concurrent tasks or processes that can be handled by the resource.
  - For CPUs, typically set to 1; for GPUs, can be greater depending on the resource's capabilities.
