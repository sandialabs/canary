CTest Discovery
===============

Canary can natively run tests defined in CTest. This is achieved by treating CTestTestfile.cmake files as inputs to a Canary test generator.

How to Run CTest Tests
----------------------

To run tests from a CMake build directory, simply pass the path to that directory to the run command:

.. code-block:: console

   python3 -m canary run path/to/cmake-build

Canary will recursively search for CTestTestfile.cmake files and generate corresponding jobs.

Key Commands
------------

*   **Discovery**: To see which CTest tests are found without running them:

    .. code-block:: console

       python3 -m canary find -r path/to/cmake-build

*   **Inspection**: To see the resolved job specification for a specific CTest test:

    .. code-block:: console

       python3 -m canary describe path/to/cmake-build/CTestTestfile.cmake

Options
-------

The extension provides specific options to the run and find commands:

*   **--ctest-config cfg**: Choose a specific CTest configuration to test.
*   **--recurse-ctest**: Force recursive search for test files. This is useful if you have a mix of CTest and other test types in the binary directory.
*   **--ctest-resource-spec-file FILE**: Specify a CTest resource specification file.

Execution Model
----------------

When a CTest test is executed, Canary wraps the original CTest command line in a shell. It ensures the process is launched in the correct working directory (defined by the CTest WORKING_DIRECTORY property) and that the required environment variables are set.
