.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Fixtures and Dependencies
==========================

Fixture Support
---------------

CTest fixtures are implemented as Canary job dependencies:

- ``FIXTURES_SETUP`` - Tests that run before the main test
- ``FIXTURES_REQUIRED`` - Fixtures required by the test
- ``FIXTURES_CLEANUP`` - Tests that run after the main test

Fixture Resolution
~~~~~~~~~~~~~~~~~~

Canary resolves fixtures by creating dependency relationships:

1. **Setup Fixtures**: Tests requiring a fixture depend on the setup fixture
2. **Cleanup Fixtures**: Cleanup fixtures depend on tests that use them

Example
~~~~~~~

.. code-block:: cmake

   add_test(setup_database "create_test_db")
   set_tests_properties(setup_database PROPERTIES FIXTURES_SETUP "db")

   add_test(test_queries "run_queries")
   set_tests_properties(test_queries PROPERTIES FIXTURES_REQUIRED "db")

   add_test(cleanup_database "drop_test_db")
   set_tests_properties(cleanup_database PROPERTIES FIXTURES_CLEANUP "db")

In this example:
- ``test_queries`` depends on ``setup_database`` (runs after setup)
- ``cleanup_database`` depends on ``test_queries`` (runs after test)

Dependency Behavior
-------------------

CTest ``DEPENDS`` vs Canary Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Key differences in dependency handling:

+----------------------------+----------------------------+----------------------------+
| Property                   | CTest Behavior             | Canary Behavior            |
+============================+============================+============================+
| ``DEPENDS``               | Execution order only       | Result consideration      |
+----------------------------+----------------------------+----------------------------+
| ``FIXTURES_REQUIRED``     | Fixture dependency        | Dependency chain          |
+----------------------------+----------------------------+----------------------------+
| ``FIXTURES_SETUP``        | Setup fixture             | Setup dependency          |
+----------------------------+----------------------------+----------------------------+
| ``FIXTURES_CLEANUP``      | Cleanup fixture           | Cleanup dependency        |
+----------------------------+----------------------------+----------------------------+

Dependency Resolution
~~~~~~~~~~~~~~~~~~~~~

Canary resolves dependencies using ``DependencySelector``:

- Dependencies are created with ``when="on_success"`` condition
- If a dependency fails, dependent tests are skipped
- Circular dependencies are detected and reported

Example with DEPENDS
~~~~~~~~~~~~~~~~~~~~

.. code-block:: cmake

   add_test(compile_code "make")
   add_test(run_tests "ctest")
   set_tests_properties(run_tests PROPERTIES DEPENDS "compile_code")

In Canary:
- ``run_tests`` depends on ``compile_code``
- If ``compile_code`` fails, ``run_tests`` will be skipped
- This is different from CTest where ``run_tests`` would still execute

See Also
--------

- :doc:`overview` - Extension overview
- :doc:`ctest-properties` - Property details
- :doc:`ctest-example` - Working example with fixtures