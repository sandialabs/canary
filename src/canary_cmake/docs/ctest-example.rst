.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

CTest Example
=============

Working Example
---------------

The ``examples/`` directory in this docs folder contains a complete working example:

.. code-block:: bash

   examples/
   ├── CTestTestfile.cmake
   ├── resource_group_test_1.py
   └── resource_group_test_2.py

CTestTestfile.cmake
~~~~~~~~~~~~~~~~~~~

The main CTest configuration file:

.. literalinclude:: examples/CTestTestfile.cmake
   :language: cmake
   :caption: CTest Configuration

This file defines three tests:

1. ``ctest_test`` - Simple test running ``ls /``
2. ``resource_group_test_1`` - Test requiring 2 GPUs (2 resource groups of 1 GPU each)
3. ``resource_group_test_2`` - Test requiring 2 CPUs and 1 GPU (1 resource group)

Resource Group Tests
~~~~~~~~~~~~~~~~~~~~

The resource group tests demonstrate CTest resource group support:

resource_group_test_1.py
^^^^^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: examples/resource_group_test_1.py
   :language: python
   :caption: Resource Group Test 1

This test:

- Validates resource group environment variables
- Requires 2 GPU resource groups (``"gpus:1,gpus:1"``)
- Prints "TEST PASSED!" on success

resource_group_test_2.py
^^^^^^^^^^^^^^^^^^^^^^^^

.. literalinclude:: examples/resource_group_test_2.py
   :language: python
   :caption: Resource Group Test 2

This test:

- Validates resource group environment variables
- Requires 1 resource group with 2 CPUs and 1 GPU (``"2,gpus:1"``)
- Prints "TEST CERTAINLY PASSED!" on success

Running the Example
-------------------

To run this example with Canary:

.. code-block:: console

   $ canary run path/to/docs/examples

Expected Output
~~~~~~~~~~~~~~~

Canary will:

1. Discover the CTest tests using ``ctest --show-only=json-v1``
2. Create job specifications for each test
3. Allocate resources from the pool
4. Execute the tests with proper environment setup
5. Report results

Test Discovery Process
----------------------

Canary discovers tests by:

1. **Finding CTestTestfile.cmake**: Locates the test definition file
2. **Parsing JSON Output**: Uses ``ctest --show-only=json-v1`` to get test metadata
3. **Creating Job Specs**: Converts CTest properties to Canary job specifications
4. **Resolving Dependencies**: Sets up fixture and dependency relationships
5. **Allocating Resources**: Maps resource groups to pool resources

Example Considerations
~~~~~~~~~~~~~~~~~~~~~~~

This example demonstrates CTest integration with resource groups. The basic ``ctest_test`` (running ``ls /``) does not require special resources, while tests with resource groups may require specific configurations.

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`resources` - Resource group details
- :doc:`ctest-properties` - Property reference