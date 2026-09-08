.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

CMake Module Reference
=======================

The ``Canary.cmake`` module provides functions for generating Canary test files from CMake.

add_canary_test
~~~~~~~~~~~~~~~

Generate a Canary test file from CMake:

.. code-block:: cmake

   add_canary_test(
     NAME <name>
     <COMMAND <command> | SCRIPT <script>>
     [NO_DEFAULT_LINK]
     [LINK link1 [link2...]]
     [KEYWORDS kwd1 [kwd2...]]
     [DEPENDS_ON dep1 [dep2...]]
   )

Parameters:

+----------------------------+----------------------------------------------------------+
| Parameter                  | Description                                              |
+============================+==========================================================+
| ``NAME``                   | Test name (required)                                     |
+----------------------------+----------------------------------------------------------+
| ``COMMAND``                | Command to execute (mutually exclusive with SCRIPT)      |
+----------------------------+----------------------------------------------------------+
| ``SCRIPT``                 | Script file to execute (mutually exclusive with COMMAND) |
+----------------------------+----------------------------------------------------------+
| ``NO_DEFAULT_LINK``        | Don't automatically link the command                     |
+----------------------------+----------------------------------------------------------+
| ``LINK``                   | Additional files to link                                 |
+----------------------------+----------------------------------------------------------+
| ``KEYWORDS``               | Test keywords                                            |
+----------------------------+----------------------------------------------------------+
| ``DEPENDS_ON``             | Test dependencies                                        |
+----------------------------+----------------------------------------------------------+

Example:

.. code-block:: cmake

   add_canary_test(
     NAME unit_test
     COMMAND my_test_program --fast
     KEYWORDS "unit" "fast"
     DEPENDS_ON build_library
   )

add_parallel_canary_test
~~~~~~~~~~~~~~~~~~~~~~~~

Generate a parallel Canary test file:

.. code-block:: cmake

   add_parallel_canary_test(
     NAME <name>
     COMMAND <command>
     NPROC <nproc1 [nproc2...]>
     [NO_DEFAULT_LINK]
     [LINK link1 [link2...]]
     [KEYWORDS kwd1 [kwd2...]]
     [DEPENDS_ON dep1 [dep2...]]
   )

Parameters:

+----------------------------+--------------------------------------------------+
| Parameter                  | Description                                      |
+============================+==================================================+
| ``NAME``                   | Test name (required)                             |
+----------------------------+--------------------------------------------------+
| ``COMMAND``                | Command to execute (required)                    |
+----------------------------+--------------------------------------------------+
| ``NPROC``                  | Number of processors (required)                  |
+----------------------------+--------------------------------------------------+
| ``NO_DEFAULT_LINK``        | Don't automatically link the command             |
+----------------------------+--------------------------------------------------+
| ``LINK``                   | Additional files to link                         |
+----------------------------+--------------------------------------------------+
| ``KEYWORDS``               | Test keywords                                    |
+----------------------------+--------------------------------------------------+
| ``DEPENDS_ON``             | Test dependencies                                |
+----------------------------+--------------------------------------------------+

Example:

.. code-block:: cmake

   add_parallel_canary_test(
     NAME mpi_integration
     COMMAND mpi_program
     NPROC 2 4 8
     KEYWORDS "integration" "mpi"
   )

add_canary_test_options
~~~~~~~~~~~~~~~~~~~~~~~~

Add options to Canary configuration:

.. code-block:: cmake

   add_canary_test_options(ON_OPTION <option>)

Parameters:

+----------------------------+--------------------------------------------------+
| Parameter                  | Description                                      |
+============================+==================================================+
| ``ON_OPTION``              | Option to enable                                 |
+----------------------------+--------------------------------------------------+

Example:

.. code-block:: cmake

   add_canary_test_options(ON_OPTION "verbose")

add_canary_test_target
~~~~~~~~~~~~~~~~~~~~~~~

Create a CMake target for running Canary tests:

.. code-block:: cmake

   add_canary_test_target()

This creates a ``canary`` target that runs Canary tests in the build directory.

write_canary_config
~~~~~~~~~~~~~~~~~~~~

Write Canary configuration file:

.. code-block:: cmake

   write_canary_config()

Generates a ``canary.yaml`` file with build information including:

- Project name and version
- Build type and date
- Source and build directories
- Compiler information
- Configured options

Example Usage
-------------

Complete CMakeLists.txt example:

.. code-block:: cmake

   cmake_minimum_required(VERSION 3.21)
   project(MyProject VERSION 1.0.0)

   # Include Canary CMake module
   include(Canary.cmake)

   # Add unit tests
   add_canary_test(
     NAME unit_test_fast
     COMMAND my_unit_test --fast
     KEYWORDS "unit" "fast"
   )

   add_canary_test(
     NAME unit_test_slow
     COMMAND my_unit_test --slow
     KEYWORDS "unit" "slow"
     DEPENDS_ON unit_test_fast
   )

   # Add MPI integration test
   find_package(MPI REQUIRED)
   add_parallel_canary_test(
     NAME mpi_integration
     COMMAND mpi_integration_test
     NPROC 2 4
     KEYWORDS "integration" "mpi"
     LINK ${MPI_C_LIBRARIES}
   )

   # Configure options
   add_canary_test_options(ON_OPTION "verbose" "color")

   # Create test target
   add_canary_test_target()

   # Write configuration
   write_canary_config()

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`ctest-example` - Working example
