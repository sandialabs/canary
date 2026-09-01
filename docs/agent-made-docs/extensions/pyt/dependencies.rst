.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Dependencies
============

The ``depends_on`` directive enables explicit dependency graphs between jobs, allowing complex workflows where tests depend on other tests completing successfully.

Dependency Basics
-----------------

Dependencies are specified using the ``depends_on`` directive:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.depends_on("setup_test")

This creates a dependency edge where the current job depends on ``setup_test``.

Dependency Selectors
--------------------

**String Selector**:

.. code-block:: python

   canary_pyt.directives.depends_on("test_name")

**Dictionary Form**:

.. code-block:: python

   canary_pyt.directives.depends_on({
       "job": "test_name",
       "when": "on_success"
   })

**Multiple Dependencies**:

.. code-block:: python

   canary_pyt.directives.depends_on("test1", "test2", "test3")

Dependency Resolution
---------------------

Canary resolves dependencies in the following order:

1. **Graph Construction**: Dependency edges are added to the job graph
2. **Topological Sort**: Jobs are ordered based on dependencies
3. **Execution**: Jobs run in dependency order
4. **Result Checking**: Dependency results are verified

Result-Sensitive Execution
--------------------------

Dependencies can be result-sensitive using the ``when`` parameter:

**on_success** (default):

.. code-block:: python

   canary_pyt.directives.depends_on("setup", when="on_success")
   # Runs only if "setup" succeeds

**on_failure**:

.. code-block:: python

   canary_pyt.directives.depends_on("setup", when="on_failure")
   # Runs only if "setup" fails

**always**:

.. code-block:: python

   canary_pyt.directives.depends_on("setup", when="always")
   # Runs regardless of "setup" result

Expected Outcomes
-----------------

Use the ``expects`` parameter to specify expected outcomes:

.. code-block:: python

   canary_pyt.directives.depends_on(
       "setup",
       expects="success"
   )

Supported values:

- ``success``: Expect dependency to pass
- ``failure``: Expect dependency to fail
- ``any``: Accept any outcome

Parameter Substitution
----------------------

Dependency names can include parameter substitutions:

.. code-block:: python

   canary_pyt.directives.parameterize("size", ["small", "large"])
   canary_pyt.directives.depends_on("setup_{size}")

Generates:

- ``test[size=small]`` depends on ``setup_small``
- ``test[size=large]`` depends on ``setup_large``

Glob Pattern Matching
---------------------

Use glob patterns to match multiple dependencies:

.. code-block:: python

   canary_pyt.directives.depends_on("setup_*")
   # Matches setup_small, setup_large, etc.

Composite Analysis
------------------

Composite analysis jobs automatically depend on their children:

.. code-block:: python

   canary_pyt.directives.aggregate(
       "analyze_results",
       ["test1", "test2", "test3"]
   )

The ``analyze_results`` job depends on ``test1``, ``test2``, and ``test3``.

See :doc:`composite-analysis` for details.

Dependency Graph
----------------

Canary builds a dependency graph and executes jobs in topological order:

.. code-block:: text

   setup_data
     ↓
   process_data
     ↓
   analyze_results
     ↓
   generate_report

Circular Dependencies
---------------------

Circular dependencies are detected and reported as errors:

.. code-block:: python

   # test1.pyt
   canary_pyt.directives.depends_on("test2")

   # test2.pyt
   canary_pyt.directives.depends_on("test1")  # Error!

Dependency Diagnostics
----------------------

Common diagnostic messages:

- ``Circular dependency detected``: Invalid dependency graph
- ``Dependency not found``: Specified job doesn't exist
- ``Dependency failed``: Dependency job failed
- ``Dependency condition not met``: ``when`` or ``expects`` condition failed

Best Practices
--------------

1. **Explicit Dependencies**:

   .. code-block:: python

      canary_pyt.directives.depends_on("setup_database")

2. **Result-Sensitive**:

   .. code-block:: python

      canary_pyt.directives.depends_on(
          "setup_database",
          when="on_success"
      )

3. **Parameterized Dependencies**:

   .. code-block:: python

      canary_pyt.directives.parameterize("config", ["a", "b"])
      canary_pyt.directives.depends_on("setup_{config}")

4. **Composite Analysis**:

   .. code-block:: python

      canary_pyt.directives.aggregate(
          "analyze",
          ["test_a", "test_b", "test_c"]
      )

Edge Cases
----------

**Missing Dependency**:

.. code-block:: python

   canary_pyt.directives.depends_on("nonexistent_test")  # Warning/Error

**Self Dependency**:

.. code-block:: python

   canary_pyt.directives.depends_on("test")  # Error: depends on itself

**Cross-File Dependencies**:

.. code-block:: python

   # test1.pyt
   canary_pyt.directives.depends_on("test2")  # OK if test2 exists

**Dynamic Dependencies**:

.. code-block:: python

   # Dependencies are static, not dynamic
   name = "test_" + str(value)
   canary_pyt.directives.depends_on(name)  # Not recommended

Runtime Access
--------------

Access dependency information at runtime:

.. code-block:: python

   def main():
       instance = canary.get_instance()
       dependencies = instance.dependencies
       for dep in dependencies:
           print(f"Depends on: {dep.name}, status: {dep.status}")

See Also
--------

- :doc:`directive-reference/depends_on`: depends_on directive reference
- :doc:`directive-reference/aggregate`: aggregate directive
- :doc:`composite-analysis`: Composite analysis overview
- :doc:`execution-model`: Execution model details
- :doc:`patterns`: Common dependency patterns
