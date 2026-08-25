.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

canary_cmake Extension Overview
================================

The ``canary_cmake`` extension provides CMake and CTest integration for Canary. It enables running CTest tests natively through Canary's execution framework and provides CMake functions for generating Canary test files.

Extension Type
--------------

- **CMake/CTest Integration**: Generator extension for CMake projects
- **Test Generator**: Creates Canary jobs from CTest test definitions
- **CMake Module**: Provides CMake functions for Canary test generation

Features
--------

1. **CTest Integration**: Run CTest tests through Canary's execution framework
2. **CMake Functions**: Generate Canary test files from CMake
3. **Resource Management**: Support for CTest resource groups
4. **Test Properties**: Support for most CTest test properties
5. **Fixture Support**: CTest fixture setup and cleanup

Usage
-----

Basic CTest Integration
~~~~~~~~~~~~~~~~~~~~~~~

To run CTest tests with Canary, simply pass the path to a CMake build directory:

.. code-block:: console

   $ canary run CMAKE_BINARY_DIR

Canary will automatically detect and run CTest tests defined in the build directory.

CMake Module Usage
~~~~~~~~~~~~~~~~~~

The ``canary_cmake`` extension provides CMake functions for generating Canary test files:

.. code-block:: cmake

   include(Canary.cmake)

   # Add a simple Canary test
   add_canary_test(
     NAME my_test
     COMMAND my_executable arg1 arg2
     KEYWORDS "unit" "fast"
     DEPENDS_ON setup_test
   )

   # Add a parallel MPI test
   add_parallel_canary_test(
     NAME mpi_test
     COMMAND mpi_program
     NPROC 2 4 8
     KEYWORDS "mpi" "parallel"
   )

Configuration
-------------

The ``canary_cmake`` extension can be configured with these options:

- ``canary_cmake_test_timeout`` - Default timeout for CTest tests (seconds)
- ``canary_cmake_ctest_config`` - CTest configuration to use

Environment Variables
~~~~~~~~~~~~~~~~~~~~

- ``CTEST_TEST_TIMEOUT`` - Timeout for CTest tests
- ``PATH`` - Used to locate CTest executable

See Also
--------

- :doc:`ctest-properties` - Supported and unsupported CTest properties
- :doc:`ctest-example` - Working CTest example
- :doc:`cmake-module` - CMake functions reference
- :doc:`status-and-regex` - Status determination and regular expressions
- :doc:`fixtures-and-dependencies` - Fixture and dependency handling