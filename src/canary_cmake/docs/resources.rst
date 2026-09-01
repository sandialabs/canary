Resources
==========

Canary maps CTest resource requirements to the Canary resource pool system.

Processor Mapping
-----------------

Canary determines the required number of CPUs in the following order of priority:
1.  **PROCESSORS property**: If defined, this value is used directly.
2.  **Command Line Inference**: Canary inspects the test command for common MPI flags (e.g., -n, -np, -c, --np). If found, the value is used as the CPU count.
3.  **Default**: If neither is found, the requirement defaults to 1 CPU.

Resource Groups
----------------

The extension supports CTest **Resource Groups**. When a job is scheduled, Canary calculates the necessary resource assignments and injects them as environment variables for the test process.

The following environment variables are provided to the test:
*   CTEST_RESOURCE_GROUP_COUNT: The number of resource groups defined.
*   CTEST_RESOURCE_GROUP_i: A comma-separated list of resource types in group $.
*   CTEST_RESOURCE_GROUP_i_TYPE: A semicolon-separated list of resource IDs and their available slots (e.g., id:gpu0,slots:1;id:gpu1,slots:1).

This allows CTest-compatible tests to discover which specific hardware resources they have been allocated.
