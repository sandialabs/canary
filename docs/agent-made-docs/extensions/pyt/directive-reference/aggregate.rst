.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

aggregate
=========

.. currentmodule:: canary_pyt.directives

.. autofunction:: aggregate

Purpose
-------

Create a composite analysis job that depends on multiple child jobs. Composite jobs are used for analysis workflows where a parent job aggregates results from multiple child jobs.

Parameters
----------

:param name: Composite job name (string)
:param children: List of child job names (list)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Creates composite parent job
- Parent depends on all child jobs
- Children are executed first
- Parent runs after children complete
- Parent has access to child results

When
----

- **Affects**: Generation phase
- **Runtime**: Composite execution

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.aggregate(
       "analyze",
       ["test1", "test2"],
       when="-o composite"
   )

Examples
--------

**Simple Composite**:

.. code-block:: python

   canary_pyt.directives.aggregate(
       "analyze_results",
       ["test1", "test2", "test3"]
   )

**Conditional Composite**:

.. code-block:: python

   canary_pyt.directives.aggregate(
       "aggregate",
       ["unit_test1", "unit_test2"],
       when="-o aggregate"
   )

**Parameterized Composite**:

.. code-block:: python

   canary_pyt.directives.parameterize("config", ["a", "b"])
   canary_pyt.directives.aggregate(
       "analyze_{config}",
       ["test_{config}_1", "test_{config}_2"]
   )

Edge Cases
----------

**Empty Children**:

.. code-block:: python

   canary_pyt.directives.aggregate("analyze", [])  # Error

**Missing Children**:

.. code-block:: python

   canary_pyt.directives.aggregate("analyze", ["nonexistent"])  # Warning

**Circular Dependency**:

.. code-block:: python

   # Composite depends on itself
   canary_pyt.directives.aggregate("analyze", ["analyze"])  # Error

Notes
-----

- Composite jobs depend on child jobs
- Children are executed first
- Parent runs after all children complete
- Parent can access child results via ``TestMultiInstance``
- Use for aggregation, analysis, and reporting workflows

Composite Workflow
------------------

1. Child jobs execute
2. Parent job waits for children
3. Parent accesses child results
4. Parent performs analysis
5. Parent generates report

Runtime Access
--------------

.. code-block:: python

   def main():
       instance = canary.get_instance()
       # Access child results
       child1 = instance.get_dependency("test1")
       child2 = instance.get_dependency("test2")
       # Aggregate results
       results = [child1.returncode, child2.returncode]

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
          "aggregate_results",
          ["unit_*", "integration_*"]
      )

3. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.aggregate(
          "report",
          ["test1", "test2"],
          when="-o generate_report"
      )

Aliases
-------

**analyze**:

.. code-block:: python

   canary_pyt.directives.analyze("report", ["test1", "test2"])  # Legacy alias

The ``analyze`` and ``aggregate`` directives are legacy aliases for ``aggregate``.

See Also
--------

- :doc:`depends_on`: Dependency directive
- :doc:`../composite-analysis`: Composite analysis overview
- :doc:`../dependencies`: Dependencies overview
