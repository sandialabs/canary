.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Selecting Jobs
==============

This document explains how Canary selects jobs for execution, covering path-based collection, filtering mechanisms, and selection strategies.

Path-Based Collection
---------------------

Canary discovers jobs by scanning filesystem paths for generators:

**Directory scanning**:

.. code-block:: console

   # Scan directory recursively
   canary collect -r path/to/tests

   # Multiple directories
   canary collect -r dir1 dir2 dir3

**File targeting**:

.. code-block:: console

   # Specific files
   canary collect -r test1.pyt test2.pyt

   # Mixed files and directories
   canary collect -r tests/ file.pyt

**Version control integration**:

.. code-block:: console

   # Git repositories
   canary collect -r git@path/to/repo

   # Other VCS
   canary collect -r repo@path/to/working_copy

Collection produces JobSpecIR objects that are resolved to JobSpecs and stored in the workspace database.

Selection Tags
--------------

Tags provide named selections of jobs for reuse:

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary init, python3 -m canary collect -r ., python3 -m canary select smoke_tests -k "basic", python3 -m canary run smoke_tests, python3 -m canary status -rA]
   :cwd: /examples

Tags are stored in the workspace database and can be reused across multiple sessions.

canary collect
--------------

The ``collect`` command discovers and stores job specifications:

.. code-block:: console

   # Basic collection
   canary collect -r path/to/tests

   # Collection with filtering
   canary collect -r . -k "smoke and unit"

   # Collection from multiple roots
   canary collect -r tests/ integration/

Collection performs:

1. Generator discovery in specified paths
2. JobSpecIR creation from generators
3. Dependency resolution
4. JobSpec storage in workspace database

canary select
-------------

The ``select`` command creates tagged job selections:

.. code-block:: console

   # Create selection from collected jobs
   canary select my_tag -k "fast and regression"

   # Create from existing tag
   canary select new_tag --from old_tag -k additional_filter

   # Create from specific roots
   canary select my_tag --from-root tests/ --from-root integration/

Selection enables targeted execution without rescanning source files.

canary find
-----------

The ``find`` command locates and displays job information:

.. code-block:: console

   # Find all jobs
   canary find -r .

   # Find with filtering
   canary find -r . -k "smoke"

   # Show dependency graph
   canary find -r . -g

   # List keywords
   canary find -r . --keywords

Find supports multiple output formats:

- **Default**: Rich display with job names and locations
- **Paths**: Grouped by root directory
- **Files**: Full file paths
- **Graph**: Dependency DAG visualization
- **Keywords**: Available keywords by root

Keyword Expressions
-------------------

Filter jobs using keyword expressions based on ``expression.py``:

**Basic keywords**:

.. code-block:: console

   # Single keyword
   canary run -k smoke .

   # Multiple keywords (OR logic)
   canary run -k "smoke unit" .

**Boolean expressions**:

.. code-block:: console

   # AND logic
   canary run -k "smoke and unit" .

   # OR logic
   canary run -k "smoke or regression" .

   # NOT logic
   canary run -k "not slow" .

   # Complex expressions
   canary run -k "(smoke or unit) and not slow" .

Keyword expressions use Python boolean syntax with job keywords as variables.

Parameter Expressions
---------------------

Filter jobs based on parameter values:

**Parameter existence**:

.. code-block:: console

   # Jobs with specific parameter
   canary run -p cpus .

**Parameter values**:

.. code-block:: console

   # Exact value match
   canary run -p "MODEL=elastic" .

   # Comparison operators
   canary run -p "cpus>2" .
   canary run -p "runtime<=30" .
   canary run -p "timeout>=60" .

**Implicit parameters**:

- ``np``: Alias for ``cpus``
- ``ndevice``: Alias for ``gpus``
- ``runtime``: Test runtime in seconds
- ``timeout``: Test timeout in seconds

Owners Filtering
----------------

Select jobs by owner attribution:

.. code-block:: console

   # Single owner
   canary run --owners alice .

   # Multiple owners
   canary run --owners alice,bob .

   # Owner expressions
   canary run --owners "alice or bob" .

Owners enable team-based job organization and responsibility tracking.

Regex Selection
---------------

Filter jobs using regular expressions:

.. code-block:: console

   # Name pattern matching
   canary run --regex "test_.*" .

   # Path pattern matching
   canary run --regex "integration/.*" .

   # Complex patterns
   canary run --regex "(smoke|regression)_test" .

Regex patterns match against job names, full names, and file paths.

ID-Based Selection
------------------

Select jobs by their unique identifiers:

.. code-block:: console

   # Single job ID
   canary run a1b2c3d

   # Multiple job IDs
   canary run job1_id job2_id job3_id

   # Partial ID matching
   canary run /a1b2  # Prefix match

Job IDs are SHA256-based identifiers that uniquely identify jobs in the workspace.

Selecting from Result Views
---------------------------

Target jobs based on previous execution results:

.. code-block:: console

   # Run from view path
   canary run ./TestResults/failed/

   # Pattern matching in view
   canary run ./TestResults/regression/%

   # Specific result locations
   canary run ./TestResults/path/to/test_case

View-based selection enables rerunning jobs based on their result locations.

Rule-Based Masking
------------------

Canary uses masking rules to exclude jobs from execution:

**Mask propagation**:

- Masked jobs are excluded from execution
- Dependencies of masked jobs may also be masked
- Masking preserves job definitions but prevents execution

**Mask reasons**:

- Filter criteria not met
- Resource constraints violated
- Dependency failures
- Manual masking via directives

Dependency Mask Propagation
---------------------------

Masking affects dependency resolution:

- If job A depends on job B
- And job B is masked
- Then job A may also be masked (depending on ``when`` condition)

**When conditions**:

- ``on_success``: Dependency must succeed
- ``on_failure``: Dependency must fail
- ``always``: Dependency must run (regardless of outcome)
- ``*``: Same as ``always``

Runtime Selection
-----------------

Selection occurs at multiple phases:

1. **Collection phase**: Generator discovery and JobSpecIR creation
2. **Resolution phase**: Dependency resolution and JobSpec creation
3. **Selection phase**: Filter application and masking
4. **Runtime phase**: Resource capacity and dependency checks

**Resource capacity checks**:

- Available CPU/GPU resources
- Memory constraints
- Node availability
- Concurrent worker limits

Rerun Selection
---------------

Rerun selection uses previous execution status:

.. code-block:: console

   # Rerun failed jobs
   canary run --only failed my_tag

   # Rerun not-passed jobs (default)
   canary run --only not_pass my_tag

   # Rerun specific status jobs
   canary run -k "not success" my_tag

Previous status becomes implicit keywords for rerun filtering.

.. _usage-filter:

Expression Syntax
-----------------

Canary uses ``expression.py`` for filtering expressions:

**Boolean operators**: ``and``, ``or``, ``not``

**Comparison operators**: ``==``, ``!=``, ``<``, ``>``, ``<=``, ``>=``

**Grouping**: Parentheses ``()`` for complex expressions

**Variables**: Job attributes (keywords, parameters, metadata)

Examples:

.. code-block:: console

   # Complex keyword expression
   canary run -k "(smoke or unit) and not slow and not broken" .

   # Parameter with comparison
   canary run -p "cpus>1 and runtime<60" .

   # Mixed criteria
   canary run -k "regression" -p "MODEL=elastic" --owners alice .

Selection Rules
---------------

Selection rules from ``rules.py``:

.. list-table:: Selection Rule Types
   :widths: 25 75
   :header-rows: 1

   * - Rule Type
     - Purpose
   * - KeywordRule
     - Filter by keyword expressions
   * - ParameterRule
     - Filter by parameter expressions
   * - OwnersRule
     - Filter by owner attribution
   * - RegexRule
     - Filter by regular expressions
   * - PrefixRule
     - Filter by path prefixes
   * - IDsRule
     - Filter by specific job IDs
   * - ResourceCapacityRule
     - Filter by available resources
   * - RerunRule
     - Filter by previous execution status
   * - SessionTimeoutRule
     - Filter by session timeout constraints

Rules are applied in sequence during the selection process.

Selection Workflow
------------------

1. **Discovery**: Find generators in specified paths
2. **Collection**: Create JobSpecIR objects from generators
3. **Resolution**: Convert JobSpecIR to JobSpec with resolved dependencies
4. **Filtering**: Apply keyword, parameter, owner, regex filters
5. **Masking**: Apply masking rules and dependency propagation
6. **Resource Check**: Verify resource capacity and constraints
7. **Final Selection**: Produce executable job list

Selection Best Practices
------------------------

1. **Use tags for common selections**: Create reusable tagged selections
2. **Combine filters effectively**: Use multiple filter types together
3. **Leverage previous status**: Use rerun strategies for efficiency
4. **Test selection criteria**: Verify filters match expected jobs
5. **Document complex selections**: Comment non-obvious filter combinations
6. **Monitor masked jobs**: Check why jobs are excluded
7. **Use views for navigation**: Browse TestResults for targeted reruns

Selection Examples
------------------

**Basic workflow testing**:

.. code-block:: console

   # Collect and select smoke tests
   canary collect -r .
   canary select smoke_tests -k smoke
   canary run smoke_tests

**Regression testing**:

.. code-block:: console

   # Run regression tests with specific parameters
   canary run -k regression -p "MODEL=elastic" .

**Performance testing**:

.. code-block:: console

   # Select performance tests by runtime
   canary run -k performance -p "runtime>30" .

**Team-based selection**:

.. code-block:: console

   # Run tests owned by specific team
   canary run --owners alice,bob,charlie .

**Complex multi-criteria**:

.. code-block:: console

   # Combine multiple filter types
   canary run -k "regression and not slow" -p "cpus>2" --owners qa_team .

Selection Troubleshooting
-------------------------

.. list-table:: Selection Issues
   :widths: 25 75
   :header-rows: 1

   * - Issue
     - Solution
   * - No jobs selected
     - Check filter criteria and paths
   * - Too many jobs selected
     - Add more specific filters
   * - Unexpected masking
     - Review mask reasons and dependencies
   * - Resource constraints
     - Adjust worker count or resource limits
   * - Dependency issues
     - Check dependency graph with ``canary find -g``

For complete command reference, see:

- :doc:`/reference/commands.collect`
- :doc:`/reference/commands.select`
- :doc:`/reference/commands.find`
