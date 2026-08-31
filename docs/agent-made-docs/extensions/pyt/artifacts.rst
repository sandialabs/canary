.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Artifacts
=========

Artifacts are files generated during job execution that should be preserved for reporting or analysis. Artifacts are collected after job execution.

artifact Directive
------------------

The ``artifact`` directive declares files to be saved:

.. code-block:: python

   canary_pyt.directives.artifact("output.txt")
   canary_pyt.directives.artifact("*.log")

Parameters
----------

**file**: File pattern to save (string)
   - Supports single files and glob patterns
   - Paths are relative to working directory

**save_on**: When to save artifact (string, default: "always")
   - ``always``: Save regardless of job outcome
   - ``success``: Save only if job succeeds
   - ``failure``: Save only if job fails

**when**: Conditional activation (WhenType)
   - Controls when artifact declaration is active

Artifact Patterns
-----------------

Glob patterns match multiple files:

.. code-block:: python

   canary_pyt.directives.artifact("*.log")
   canary_pyt.directives.artifact("output/*.txt")
   canary_pyt.directives.artifact("**/*.csv")

When Artifacts Are Collected
-----------------------------

Artifacts are collected during job cleanup:

1. Job executes
2. Job completes (success or failure)
3. Artifacts are collected based on ``save_on``
4. Artifacts are saved to results directory
5. Artifacts are available in reports

Save On Values
--------------

**always** (default):

.. code-block:: python

   canary_pyt.directives.artifact("output.txt", save_on="always")

**success**:

.. code-block:: python

   canary_pyt.directives.artifact("result.txt", save_on="success")

**failure**:

.. code-block:: python

   canary_pyt.directives.artifact("error.log", save_on="failure")

Assets vs Artifacts
-------------------

**Assets**:

- Files needed **before** execution
- Input files, test data, configuration
- Set up in workspace before job runs
- Use ``copy``, ``link``, ``sources`` directives

**Artifacts**:

- Files saved **after** execution
- Output files, logs, results
- Collected after job completes
- Use ``artifact`` directive

Examples
--------

**Save Output File**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.artifact("result.txt")

**Save Log Files**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.artifact("*.log")

**Save on Failure**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.artifact("error.log", save_on="failure")

**Save on Success**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.artifact("output.txt", save_on="success")

**Conditional Artifact**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.artifact("debug.log", when="-o debug")

Best Practices
--------------

1. **Save Output Files**:

   .. code-block:: python

      canary_pyt.directives.artifact("result.txt")

2. **Save Log Files**:

   .. code-block:: python

      canary_pyt.directives.artifact("*.log")

3. **Save on Failure for Debugging**:

   .. code-block:: python

      canary_pyt.directives.artifact("error.log", save_on="failure")

4. **Conditional Artifacts**:

   .. code-block:: python

      canary_pyt.directives.artifact("debug.txt", when="-o debug")

5. **Document Purpose**:

   .. code-block:: python

      # Save test output for analysis
      canary_pyt.directives.artifact("output.csv")

See Also
--------

- :doc:`directive-reference/artifact`: Artifact directive
- :doc:`assets`: Assets overview
- :doc:`baselines`: Baselines overview
