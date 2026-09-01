Fixtures and Dependencies
==========================

Canary handles CTest dependencies and fixtures by translating them into its own dependency graph.

Dependency Semantics
--------------------

**CTest DEPENDS property**: In CTest, DEPENDS establishes a strict execution order. In Canary, this is converted into a dependency that is **result-sensitive**. By default, if a dependency fails, the dependent job is blocked.

**CTest Fixtures**:
Canary implements the CTest fixture model using dependency links:

1.  **FIXTURES_SETUP**: Jobs that set up a fixture are identified.
2.  **FIXTURES_REQUIRED**: Jobs requiring a fixture depend on all jobs that set up that fixture.
3.  **FIXTURES_CLEANUP**: Cleanup jobs depend on all jobs that require the fixture.

This ensures that the setup runs before the test, and the cleanup runs after the test has completed.

Behavioral Difference
---------------------

It is important to note that Canary's dependency model is more restrictive than CTest's. In CTest, a dependency might only control order. In Canary, a failed dependency typically prevents the execution of the dependent job to avoid cascading failures.
