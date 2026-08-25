.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Resource Groups
===============

Resource Group Support
----------------------

Canary maps CTest ``RESOURCE_GROUPS`` to its resource pool system:

.. code-block:: cmake

   add_test(my_test "my_program")
   set_tests_properties(my_test PROPERTIES RESOURCE_GROUPS "2,gpus:1")

This creates a resource requirement for 2 CPUs and 1 GPU.

Resource Group Format
~~~~~~~~~~~~~~~~~~~~

CTest resource groups use the format:

.. code-block:: cmake

   RESOURCE_GROUPS "<cpus>,<type>:<slots>[;<type>:<slots>...]"

Examples:

- ``"2,gpus:1"`` - 2 CPUs + 1 GPU
- ``"gpus:1,gpus:1"`` - 2 GPUs (different instances)
- ``"4"`` - 4 CPUs only

Resource Group Variables
------------------------

Canary sets environment variables for resource groups:

+------------------------------------+--------------------------------------------------+
| Variable                           | Description                                      |
+====================================+==================================================+
| ``CTEST_RESOURCE_GROUP_COUNT``    | Number of resource groups                        |
+------------------------------------+--------------------------------------------------+
| ``CTEST_RESOURCE_GROUP_<N>``      | Resource types in group N                        |
+------------------------------------+--------------------------------------------------+
| ``CTEST_RESOURCE_GROUP_<N>_<TYPE>``| Resource specifications for type in group N      |
+------------------------------------+--------------------------------------------------+

Example
~~~~~~~

For ``RESOURCE_GROUPS "2,gpus:1"``:

- ``CTEST_RESOURCE_GROUP_COUNT="1"``
- ``CTEST_RESOURCE_GROUP_0="gpus"``
- ``CTEST_RESOURCE_GROUP_0_GPUS="id:<gpu_id>,slots:<slots>"``

See the example in ``examples/ctest/resource_group_test_1.py``:

.. literalinclude:: ../../../../examples/ctest/resource_group_test_1.py
   :language: python
   :caption: Resource Group Test Example

Resource Allocation
-------------------

Canary allocates resources from the pool:

1. **Resource Discovery**: Canary discovers available resources
2. **Group Mapping**: Resource groups are mapped to pool resources
3. **Environment Setup**: Resource variables are set before test execution
4. **Validation**: Insufficient resources cause test failure

Limitations
~~~~~~~~~~~

- Resource group mapping has limitations with certain resource types
- GPU resource IDs are normalized (``NVIDIA:`` and ``AMD:`` prefixes removed)
- Resource allocation failures result in ``ValueError``

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`ctest-properties` - Property reference
- :doc:`ctest-example` - Complete working example