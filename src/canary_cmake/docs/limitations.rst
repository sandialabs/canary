Limitations and Diagnostics
============================

Integration with CMake and CTest is powerful but has certain constraints.

Limitations
------------

*   **CMake Version**: The CTest integration requires CMake > 3.20.
*   **CTest Tool Requirement**: The canary_cmake extension relies on the ctest binary being present on the system to discover tests via ctest --show-only=json-v1. If ctest is missing, jobs cannot be generated.
*   **Ordering vs. Dependencies**: As noted in the Fixtures section, CTest DEPENDS is purely for ordering. Canary converts these to result-sensitive dependencies.
*   **Working Directory**: Canary assumes that the working directory provided by CTest is relative to the build tree.
*   **Unsupported Properties**: Several CTest properties (e.g., COST, MEASUREMENT) are not supported and will trigger a warning.

Common Failures and Diagnostics
-------------------------------

*   **cmake not found**: If you see this warning, ensure CMake is installed and in your PATH.
*   **Missing Tests**: If Canary finds no tests in a directory, verify that it contains a CTestTestfile.cmake and that you are pointing to the build directory, not the source directory.
*   **Wrong Working Directory**: If tests fail because they cannot find their assets, inspect the WORKING_DIRECTORY property in the CTest file and compare it with where Canary is executing the job.
