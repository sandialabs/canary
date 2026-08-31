.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-dependencies:

Dependencies
============

Canary's dependency system manages relationships between jobs, enabling complex workflows where tests depend on the successful completion of other tests. This system supports execute-and-analyze patterns, multi-stage workflows, and conditional execution.

Dependency Model
----------------

Dependencies are directed relationships where a job (the dependent) requires another job (the dependency) to complete before it can execute. Dependencies form a directed acyclic graph (DAG) that determines execution order.

Key Concepts:

- **Dependency**: A job that must complete before another job can run
- **Dependent**: A job that requires dependencies to complete first
- **Dependency Graph**: The complete set of relationships between jobs
- **Topological Order**: Execution order determined by dependency resolution

Defining Dependencies
---------------------

Dependencies are defined in test files using directives:

.. code-block:: python

   import canary_pyt

   # Simple dependency on another test
   canary_pyt.directives.depends_on("other_test.pyt")

   # Dependency with conditional execution
   canary_pyt.directives.depends_on("setup_test.pyt", when="on_success")

Dependency Resolution
---------------------

The dependency resolver:

1. **Pattern Matching**: Resolves dependency patterns to specific job IDs
2. **Graph Construction**: Builds the dependency DAG from resolved relationships
3. **Topological Sorting**: Determines execution order based on dependencies
4. **Conditional Evaluation**: Checks dependency conditions (e.g., "on_success")

Dependency Patterns
-------------------

Dependencies can be specified using patterns:

- **Exact Match**: ``depends_on("test_id")``
- **Glob Pattern**: ``depends_on("setup_*")``
- **Family Match**: ``depends_on("family:setup")``
- **Tag Match**: ``depends_on("@setup")``

Example:

.. code-block:: python

   # Depend on all tests in the setup family
   canary_pyt.directives.depends_on("family:setup")

   # Depend on tests tagged as @prerequisite
   canary_pyt.directives.depends_on("@prerequisite")

Dependency Conditions
---------------------

Dependencies support conditional execution:

- **always** (or "*"): Always execute dependency (default)
- **on_success**: Execute only if dependency succeeds
- **on_failure**: Execute only if dependency fails

Example:

.. code-block:: python

   # Cleanup runs only if main test succeeds
   canary_pyt.directives.depends_on("main_test.pyt", when="on_success")

   # Recovery runs only if main test fails
   canary_pyt.directives.depends_on("main_test.pyt", when="on_failure")

Dependency Groups
-----------------

Dependencies can be organized into groups for conditional execution:

.. code-block:: python

   # Group 1: Setup dependencies (must all succeed)
   canary_pyt.directives.depends_on("setup_db.pyt", group=1)
   canary_pyt.directives.depends_on("setup_cache.pyt", group=1)

   # Group 2: Optional dependencies (at least one must succeed)
   canary_pyt.directives.depends_on("fast_path.pyt", group=2)
   canary_pyt.directives.depends_on("slow_path.pyt", group=2)

Execute-and-Analyze Pattern
---------------------------

A common pattern where parameterized tests execute first, then a base analysis test runs:

.. code-block:: python

   import canary

   # Generate parameterized tests
   canary_pyt.directives.parameterize("a", [1, 2, 3])

   # Base test depends on all parameterized instances
   canary_pyt.directives.aggregate()

This creates:

1. ``test.a=1``, ``test.a=2``, ``test.a=3`` (parameterized tests)
2. ``test`` (base test that depends on all parameterized tests)

Dependency Graph Visualization
------------------------------

View the dependency graph using:

.. code-block:: console

   $ canary describe test_file.pyt

   test_file.pyt (base)
   ├── test_file.a=1.pyt
   ├── test_file.a=2.pyt
   └── test_file.a=3.pyt

Dependency Resolution Process
-----------------------------

1. **Collection**: Gather all job specifications
2. **Pattern Resolution**: Match dependency patterns to specific jobs
3. **Graph Construction**: Build the complete dependency DAG
4. **Validation**: Check for cycles and missing dependencies
5. **Topological Sort**: Determine execution order
6. **Execution**: Run jobs in dependency order

Dependency Management Commands
------------------------------

- ``canary describe``: Show dependency relationships
- ``canary select --dependencies``: Select jobs with their dependencies
- ``canary run --only=dependencies``: Run only dependencies

Best Practices
--------------

- **Explicit Dependencies**: Clearly document why dependencies exist
- **Minimal Dependencies**: Only depend on what's necessary
- **Conditional Execution**: Use conditions to optimize workflows
- **Avoid Cycles**: Ensure dependency graph is acyclic
- **Group Related Dependencies**: Use groups for logical organization

Troubleshooting
---------------

**Circular Dependency**:

.. code-block:: console

   $ canary run my_test.pyt
   Error: Circular dependency detected: A -> B -> C -> A

Solution: Restructure dependencies to remove cycles.

**Missing Dependency**:

.. code-block:: console

   $ canary run my_test.pyt
   Error: Unresolved dependency: required_test not found

Solution: Ensure the required test exists and is discoverable.

**Dependency Condition Not Met**:

.. code-block:: console

   $ canary run my_test.pyt
   Warning: Skipping my_test.pyt: dependency condition not satisfied

Solution: Check dependency execution status and conditions.

See Also
--------

- :doc:`concepts`: Core architectural concepts
- :doc:`jobs`: Job structure and lifecycle
- :doc:`running`: Execution with dependency management
- :doc:`selection`: Selecting jobs with dependencies
- :doc:`/reference/commands.describe`: Describe command reference
