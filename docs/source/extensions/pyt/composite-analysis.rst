.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Composite Analysis
==================

Composite analysis enables workflows where a parent job aggregates results from multiple child jobs. This is useful for analysis, reporting, and multi-stage workflows.

aggregate Directive
-------------------

Create a composite analysis job:

.. code-block:: python

   canary_pyt.directives.aggregate(
       "analyze",
       ["test1", "test2", "test3"]
   )

**Parameters**:

- **name**: Composite job name (string)
- **children**: List of child job names (list)
- **when**: Conditional activation (WhenType)

Parameterized Child Jobs
------------------------

Child jobs can be parameterized:

.. code-block:: python

   canary_pyt.directives.parameterize("config", ["a", "b"])
   canary_pyt.directives.aggregate(
       "analyze_{config}",
       ["test_{config}_1", "test_{config}_2"]
   )

Dependency Relationship
-----------------------

Composite jobs depend on child jobs:

1. Child jobs execute first
2. Parent job waits for all children
3. Parent job executes after children complete
4. Parent can access child results

.. code-block:: text

   test1 → analyze
   test2 → analyze
   test3 → analyze

Flag and Script
---------------

**flag**:
   Pass flag to composite job

.. code-block:: python

   canary_pyt.directives.aggregate(
       "analyze",
       ["test1", "test2"],
       flag="--analyze"
   )

**script**:
   Use script for composite analysis

.. code-block:: python

   canary_pyt.directives.aggregate(
       "analyze",
       ["test1", "test2"],
       script="analyze.sh"
   )

requires Parameter
------------------

Specify required child jobs:

.. code-block:: python

   canary_pyt.directives.aggregate(
       "analyze",
       requires=["test1", "test2"]
   )

Example: Running Composite Analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary run ./execute_and_analyze, python3 -m canary status -rA, python3 -m canary tree TestResults]
   :cwd: /examples

This example demonstrates running tests with composite analysis, showing the dependency tree structure.

TestMultiInstance
-----------------

Access child job results via ``TestMultiInstance``:

.. code-block:: python

   def main():
       instance = canary.get_instance()

       # Access child results
       child1 = instance.get_dependency("test1")
       child2 = instance.get_dependency("test2")

       # Aggregate results
       results = {
           "test1": child1.returncode,
           "test2": child2.returncode
       }

Child Job Parameters
--------------------

Access child job parameters:

.. code-block:: python

   def main():
       instance = canary.get_instance()

       # Get child dependencies
       for child in instance.dependencies:
           print(f"Child: {child.name}")
           print(f"Parameters: {child.parameters}")
           print(f"Return code: {child.returncode}")

Examples
--------

**Simple Composite**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.aggregate(
       "analyze_results",
       ["test1", "test2", "test3"]
   )

**Parameterized Composite**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.parameterize("size", ["small", "large"])
   canary_pyt.directives.aggregate(
       "analyze_{size}",
       ["test_{size}_1", "test_{size}_2"]
   )

**With Flag**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.aggregate(
       "analyze",
       ["test1", "test2"],
       flag="--analyze"
   )

**Conditional Composite**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.aggregate(
       "report",
       ["test1", "test2"],
       when="-o generate_report"
   )

Best Practices
--------------

1. **Analysis Jobs**:

   .. code-block:: python

      canary_pyt.directives.aggregate(
          "analyze",
          ["test1", "test2", "test3"]
      )

2. **Aggregation**:

   .. code-block:: python

      canary_pyt.directives.aggregate(
          "aggregate",
          ["unit_*", "integration_*"]
      )

3. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.aggregate(
          "report",
          ["test1", "test2"],
          when="-o report"
      )

4. **Parameterized**:

   .. code-block:: python

      canary_pyt.directives.parameterize("config", ["a", "b"])
      canary_pyt.directives.aggregate(
          "analyze_{config}",
          ["test_{config}_1", "test_{config}_2"]
      )

Limitations
-----------

**Circular Dependencies**:
   Composite jobs cannot depend on themselves

**Missing Children**:
   Warning if child jobs do not exist

**Failed Children**:
   Composite job fails if required children fail

See Also
--------

- :doc:`directive-reference/aggregate`: Composite directive
- :doc:`dependencies`: Dependencies overview
- :doc:`test-instance`: Test instance access
