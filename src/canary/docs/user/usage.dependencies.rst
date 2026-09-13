.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-dependencies:

Job dependencies
================

``canary``'s dependency system manages relationships between jobs, enabling complex
workflows where tests depend on the successful completion of other tests.  This system
supports execute-and-analyze patterns, multi-stage workflows, and conditional
execution.

Dependency model
----------------

Dependencies are directed relationships where a job (the *dependent*) requires another
job (the *dependency*) to complete before it can execute.  Together, all dependency
relationships form a directed acyclic graph (DAG) that determines execution order.

Key concepts:

- **Dependency**: a job that must complete before another job can run
- **Dependent**: a job that requires one or more dependencies to complete first
- **Dependency graph**: the complete set of relationships between jobs
- **Topological order**: the execution order determined by the graph

Defining dependencies
---------------------

Dependencies are declared in ``.pyt`` test files using the ``depends_on`` directive:

.. code-block:: python

   import canary

   # Simple dependency on another test
   canary.directives.depends_on("other_test.pyt")

   # Dependency with conditional execution
   canary.directives.depends_on("setup_test.pyt", when="on_success")

Dependency patterns
-------------------

The first argument to ``depends_on`` is a pattern matched against the names of jobs
in the same collection:

- **Exact match**: ``depends_on("test_id")``
- **Glob pattern**: ``depends_on("setup_*")``
- **Family match**: ``depends_on("family:setup")``
- **Tag match**: ``depends_on("@setup")``

Example:

.. code-block:: python

   # Depend on all jobs in the setup family
   canary.directives.depends_on("family:setup")

   # Depend on jobs tagged as @prerequisite
   canary.directives.depends_on("@prerequisite")

Dependency conditions
---------------------

The ``when`` argument controls when the dependent job runs relative to the outcome
of its dependency:

- **always** (or ``"*"``) — always run the dependent regardless of outcome *(default)*
- **on_success** — run only if the dependency succeeds
- **on_failure** — run only if the dependency fails

.. code-block:: python

   # Cleanup step only if main test succeeded
   canary.directives.depends_on("main_test.pyt", when="on_success")

   # Recovery step only if main test failed
   canary.directives.depends_on("main_test.pyt", when="on_failure")

If a condition is not met, the dependent job receives a ``blocked`` status rather than
running.

Dependency groups
-----------------

Multiple ``depends_on`` calls can be assigned to groups for collective evaluation.
Within a group, *all* dependencies must satisfy their condition for the group to
be considered met.  All groups must be met for the dependent to run.

.. code-block:: python

   # Group 1: both setup steps must succeed
   canary.directives.depends_on("setup_db.pyt", group=1)
   canary.directives.depends_on("setup_cache.pyt", group=1)

   # Group 2: at least one data-loading path must succeed
   canary.directives.depends_on("fast_path.pyt", group=2)
   canary.directives.depends_on("slow_path.pyt", group=2)

Execute-and-analyze pattern
---------------------------

A common pattern runs parameterized child tests first, then a base (aggregate)
test that consumes their results.  The ``aggregate`` directive creates this
relationship automatically:

.. code-block:: python

   import canary

   # Parameterized children are created automatically
   canary.directives.parameterize("a", [1, 2, 3])

   # This test runs after all parameterized instances complete
   canary.directives.aggregate()

This creates four jobs: ``test.a=1``, ``test.a=2``, ``test.a=3``, and ``test``
(the base test that depends on all three).  See :ref:`usage-execute-and-analyze` for
a worked example.

Visualizing the dependency graph
---------------------------------

Use ``canary describe`` to inspect the dependency structure of a test file:

.. code-block:: console

   $ canary describe test_file.pyt

   test_file.pyt (base)
   ├── test_file.a=1.pyt
   ├── test_file.a=2.pyt
   └── test_file.a=3.pyt

Dependency resolution process
------------------------------

1. **Collection** — gather all job specifications from generators
2. **Pattern resolution** — match dependency patterns to specific job IDs
3. **Graph construction** — build the complete dependency DAG
4. **Validation** — check for cycles and missing dependencies
5. **Topological sort** — determine execution order
6. **Execution** — run jobs in dependency order

Dependency management commands
-------------------------------

- ``canary describe`` — show dependency relationships for a test file
- ``canary select --dependencies`` — include transitive dependencies in a selection
- ``canary find -g`` — display the full dependency graph

Best practices
--------------

- **Be explicit**: document why each dependency exists
- **Keep it minimal**: only depend on what is strictly necessary
- **Use conditions**: ``on_success`` / ``on_failure`` to build robust workflows
- **Avoid cycles**: the resolver will reject circular dependencies
- **Group logically**: use groups to express multi-prerequisite requirements

Troubleshooting
---------------

**Circular dependency detected**

.. code-block:: console

   $ canary run my_test.pyt
   Error: Circular dependency detected: A -> B -> C -> A

Restructure the dependency graph to eliminate the cycle.

**Missing dependency**

.. code-block:: console

   $ canary run my_test.pyt
   Error: Unresolved dependency: required_test not found

Ensure the required test exists within the same collection root and is discoverable
by the generator.

**Dependency condition not met**

.. code-block:: console

   $ canary status
   ...  blocked  dependency condition not satisfied

Check the status of the dependency job; the blocking job may itself have failed or
been skipped.

See Also
--------

- :ref:`basics-concepts` — core architectural concepts
- :ref:`basics-job` — job structure and lifecycle
- :ref:`usage-run-basic` — execution with dependency management
- :ref:`usage-execute-and-analyze` — execute-and-analyze worked example
