.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Running Workflows and Tests
===========================

This document explains how to run workflows and tests with Canary, covering basic execution patterns, advanced options, and workflow management.

Basic Run Workflow
------------------

The basic workflow for running tests with Canary:

1. **Discovery**: Canary finds job generators in specified paths
2. **Collection**: Job generators produce JobSpecIR objects
3. **Resolution**: Canary resolves dependencies and creates JobSpecs
4. **Selection**: Jobs are filtered based on criteria
5. **Execution**: Canary runs jobs in a new session
6. **Persistence**: Results are stored in the workspace database
7. **View Update**: TestResults view is refreshed

Simple execution from current directory:

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary run ./basic, python3 -m canary status -rA]
   :cwd: /examples

This scans the basic examples directory recursively for job generators and executes all discovered jobs.

Running from Paths
------------------

Canary accepts various path specifications for test discovery:

**Directory scanning**:

.. code-block:: console

   # Scan directory recursively
   canary run path/to/tests

   # Scan multiple directories
   canary run path1 path2 path3

**File execution**:

.. code-block:: console

   # Run specific file
   canary run path/to/test.pyt

   # Run multiple files
   canary run file1.pyt file2.pyt file3.pyt

**Version control prefixes**:

.. code-block:: console

   # Git repository scanning
   canary run git@path/to/repo

   # Other version control systems
   canary run repo@path/to/working_copy

**Root:path style**:

.. code-block:: console

   # Explicit root and relative path
   canary run /absolute/root:relative/path/test.pyt

Running from Selected Tags
--------------------------

Canary supports tagged selections for targeted execution:

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary init ., python3 -m canary collect -r ., python3 -m canary select quick_tests -k "basic", python3 -m canary run quick_tests, python3 -m canary status -rA]
   :cwd: /examples

Tags enable reusable job selections with specific filtering criteria.

Running from View Paths
-----------------------

Execute jobs found in result view paths:

.. code-block:: console

   # Run jobs from specific view path
   canary run ./TestResults/subdirectory

   # Run jobs matching view pattern
   canary run ./TestResults/path/to/%

View-based execution targets jobs whose results appear in the specified TestResults locations.

Rerun Behavior
--------------

Canary's rerun behavior depends on the ``--only`` strategy:

**Default behavior** (``--only not_pass``):

- Only runs jobs that did not pass in previous execution
- Skips jobs that were successful
- Includes jobs that failed, diffed, or were not run

**Explicit rerun strategies**:

.. list-table:: Rerun Strategies
   :widths: 25 75
   :header-rows: 1

   * - Strategy
     - Behavior
   * - ``all``
     - Run all jobs regardless of previous status
   * - ``failed``
     - Run only jobs that failed in previous execution
   * - ``not_pass``
     - Run jobs that did not pass (default)
   * - ``not_run``
     - Run only jobs that were not executed previously
   * - ``changed``
     - Run jobs with changed source files or dependencies

Examples:

.. code-block:: text

   # Run all jobs
   canary run --only all my_tag

   # Run only failed jobs
   canary run --only failed my_tag

   # Run jobs that weren't executed
   canary run --only not_run my_tag

Empty Test Set Handling
-----------------------

By default, Canary treats empty test sets as errors:

.. code-block:: console

   # This exits with code 7 if no tests match
   canary run -k "nonexistent_keyword" .

Use ``--empty-ok`` to allow empty test sets:

.. code-block:: console

   # Exit normally (code 0) when no tests match
   canary run --empty-ok -k "nonexistent_keyword" .

Fail-Fast Execution
-------------------

Stop execution after the first failure:

.. code-block:: console

   # Stop at first failed job
   canary run --fail-fast .

This is useful for:

- Quick feedback during development
- Identifying first failure in a sequence
- Debugging complex workflows

Worker Configuration
--------------------

Control parallel execution with ``--workers``:

.. code-block:: console

   # Limit to 4 concurrent workers
   canary run --workers 4 .

   # Single-threaded execution
   canary run --workers 1 .

Worker count affects:

- Resource utilization
- Execution speed
- System load
- Dependency handling

Timeout Options
---------------

Canary supports multiple timeout configurations:

**Session timeout**:

.. code-block:: console

   # Limit entire session to 1 hour
   canary run --timeout session=1h .

**Per-job timeout**:

.. code-block:: console

   # Set default job timeout
   canary run --timeout default=30m .

   # Override specific job keywords
   canary run --timeout slow=2h --timeout fast=5m .

Timeout format uses Go-style durations:

- ``30s`` - 30 seconds
- ``5m`` - 5 minutes
- ``2h`` - 2 hours
- ``1h30m`` - 1 hour 30 minutes
- ``4h30m30s`` - 4 hours 30 minutes 30 seconds

Script Arguments
----------------

Pass arguments to test scripts using ``--``:

.. code-block:: console

   # Arguments after -- are passed to scripts
   canary run . -- --verbose --debug

This enables:

- Script-specific configuration
- Runtime parameters
- Debug flags
- Custom arguments

Cleaning Work Directories
-------------------------

Remove existing work directories with ``-w``:

.. code-block:: console

   # Remove and recreate work directories
   canary run -w .

This ensures:

- Clean execution environment
- No leftover artifacts
- Fresh workspace setup
- Consistent results

Relationship to Workspaces and Sessions
---------------------------------------

Running workflows interacts with workspaces and sessions:

**Workspace interaction**:

1. **Discovery**: Canary scans paths in the workspace context
2. **Collection**: JobSpecs are stored in workspace database
3. **Selection**: Filtered specs are cached in workspace
4. **Execution**: Session runs within workspace
5. **Persistence**: Results stored in workspace database

**Session creation**:

- Each ``canary run`` creates a new session (unless reusing)
- Session contains executed jobs and their results
- Session manifest stored in ``.canary/sessions/{name}/session.lock``
- Latest session referenced in ``.canary/refs/latest``

**Result views**:

- TestResults view updated after successful execution
- View contains symlinks/hardlinks to latest results
- Organized by source tree structure
- Enables easy navigation of results

Advanced Run Patterns
---------------------

**Pathspec files**:

.. code-block:: console

   # Run from YAML/JSON pathspec file
   canary run -f testpaths.yaml

Pathspec file format:

.. code-block:: yaml

   testpaths:
     - root: /path/to/tests
       paths:
         - test1.pyt
         - test2.pyt
     - root: /another/path
       paths:
         - suite1/
         - suite2/

**Tag management**:

.. code-block:: console

   # Create and run tagged selection
   canary select my_tag -k "smoke and unit"
   canary run my_tag

   # Delete old tag
   canary select --delete old_tag

**View-based workflow**:

.. code-block:: console

   # Run from specific view locations
   canary run ./TestResults/failed/
   canary run ./TestResults/regression/%

**ID-based execution**:

.. code-block:: console

   # Run specific job by ID
   canary run a1b2c3d4e5f6

   # Run multiple jobs by ID
   canary run job1_id job2_id job3_id

Run Configuration Summary
-------------------------

.. list-table:: Common Run Options
   :widths: 25 75
   :header-rows: 1

   * - Option
     - Purpose
   * - ``--only {all,failed,not_pass,not_run,changed}``
     - Control rerun strategy
   * - ``--empty-ok``
     - Allow empty test sets
   * - ``--fail-fast``
     - Stop at first failure
   * - ``--workers N``
     - Limit concurrent workers
   * - ``--timeout session=T``
     - Limit session duration
   * - ``--timeout default=T``
     - Set default job timeout
   * - ``-w``
     - Clean work directories
   * - ``--``
     - Pass arguments to scripts
   * - ``-f file``
     - Read paths from file

For complete command reference, see :doc:`/reference/commands.run`.
