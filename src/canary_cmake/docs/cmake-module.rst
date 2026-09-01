CMake Module
=============

The canary_cmake extension provides a bundled CMake module, Canary.cmake, which allows developers to define Canary tests directly within their CMakeLists.txt files.

How to Use
-----------

The Canary.cmake module should be included in your project:

.. code-block:: cmake

   include(Canary)

This module provides several functions to generate .pyt (Python Test) files in the build directory, which Canary can then discover and run.

Key Functions
--------------

**add_canary_test()**
Adds a basic Canary unit test.
*   **Required**: NAME and either COMMAND or SCRIPT.
*   **Optional**: LINK (files to link), KEYWORDS (Canary keywords), DEPENDS_ON (other tests).
*   **Behavior**: If COMMAND is used, it generates a  file that wraps the command in a Python function. If SCRIPT is used, it copies the script to the build directory as a  file.

**add_parallel_canary_test()**
Adds a test that is parameterized by the number of processors.
*   **Required**: NAME, COMMAND, and NPROC (a list of processor counts).
*   **Behavior**: Generates a  file that uses canary.directives.parameterize("cpus", [...]).

**add_canary_test_options()**
Adds options to the Canary CLI for this project.
*   **Usage**: add_canary_test_options(ON_OPTION opt1 opt2).
*   **Behavior**: Sets the CANARY_ON_OPTIONS cache variable, which is used by write_canary_config().

**add_canary_test_target()**
Adds a custom CMake target named canary that runs the tests.
*   **Usage**: add_custom_target(canary ... COMMAND canary run -w .).

**write_canary_config()**
Generates a canary.yaml configuration file in the build directory.
*   **Details**: Captures project name, version, build type, compiler info, and the options set via add_canary_test_options.

Example CMakeLists.txt
----------------------

.. code-block:: cmake

   cmake_minimum_required(VERSION 3.20)
   project(MyProject VERSION 1.0)

   include(Canary)

   add_executable(my_test_bin main.cpp)
   
   # Add a serial Canary test
   add_canary_test(
     NAME a_basic_test
     COMMAND my_test_bin --arg1 val1
     KEYWORDS smoke stability
   )

   # Add a parallel Canary test run on 1, 2, and 4 CPUs
   add_parallel_canary_test(
     NAME a_parallel_test
     COMMAND mpiexec my_test_bin
     NPROC 1 2 4
     KEYWORDS mpi
   )

   write_canary_config()
   add_canary_test_target()
