CTest Example
=============

The project includes a working example of CTest integration in the examples/ctest directory.

Example Structure
-----------------

The example contains:
*   CTestTestfile.cmake: Defines the tests.
*   resource_group_test_1.py & resource_group_test_2.py: Python scripts that verify resource allocation.
*   Testing/: The directory where CTest normally stores its state.

Running the Example
-------------------

To exercise the CTest integration, you can use the following workflow:

.. code-block:: console

   # 1. Create a build directory and configure the project
   cmake -S examples/ctest -B examples/ctest/build
   
   # 2. Run the tests using Canary
   python3 -m canary run examples/ctest/build
   
   # 3. Inspect the results
   python3 -m canary status -rA

How it Works in the Example
---------------------------

The example demonstrates how CTest properties are mapped to Canary. For instance, if the tests in the example define PROCESSORS or RESOURCE_GROUPS in their CTest definition, Canary will respect these requirements and assign the appropriate resources from its pool before executing the scripts.
