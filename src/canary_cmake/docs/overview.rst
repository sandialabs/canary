Overview
========

The canary_cmake extension allows Canary to integrate with CMake-based projects. It provides the ability to discover tests defined via CTest and offers tools to generate Canary-compatible test definitions directly from CMake.

Relationship to Canary
-----------------------

canary_cmake is an extension package that contributes CMake and CTest integration to the Canary ecosystem. Its primary role is to act as a **job generator**.

It provides a specialized generator for CTestTestfile.cmake files. When Canary encounters these files, the extension transforms the CTest metadata into Canary job specifications.

It is important to note that:
*   **CTest is an input format**: Canary treats CTest definitions as one of many ways to define jobs.
*   **Core responsibilities remain with Canary**: The Canary core engine remains responsible for selection, dependency resolution, scheduling, execution, persistence, and reporting.
*   **Independence**: You do not need to use CMake to use Canary, but if you do, this extension allows you to leverage your existing CTest infrastructure.

Main Capabilities
------------------

1.  **CTest Discovery**: Automatically find and run tests defined in a CMake build directory.
2.  **CMake Module**: A bundled CMake module (Canary.cmake) that provides functions to generate .pyt test files during the CMake configuration phase.
3.  **Property Mapping**: Translation of CTest properties (like labels, environment, and timeouts) into Canary attributes and parameters.
