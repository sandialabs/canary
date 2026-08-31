.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

artifact
========

.. currentmodule:: canary_pyt.directives

.. autofunction:: artifact

Purpose
-------

Declare expected artifact files that should be saved from the job. Artifacts are files generated during test execution that should be preserved for reporting or analysis.

Parameters
----------

:param file: File pattern to save (string)
:param when: Optional conditional activation (WhenType)
:param save_on: When to save artifact (string, default: "always")

Effect on Generated Jobs
------------------------

- Records artifact patterns for the job
- Artifacts are saved based on ``save_on`` condition
- Saved artifacts are available in reports
- Artifact patterns support globs

When
----

- **Affects**: Generation phase (artifact recording)
- **Runtime**: Artifacts saved during cleanup

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.artifact("output.txt", when="-o save_output")

Examples
--------

**Single Artifact**:

.. code-block:: python

   canary_pyt.directives.artifact("result.txt")

**Multiple Artifacts**:

.. code-block:: python

   canary_pyt.directives.artifact("*.log")

**Conditional Artifact**:

.. code-block:: python

   canary_pyt.directives.artifact("debug.log", when="-o debug")

**Save on Failure**:

.. code-block:: python

   canary_pyt.directives.artifact("error.log", save_on="failure")

**Save on Success**:

.. code-block:: python

   canary_pyt.directives.artifact("output.txt", save_on="success")

Edge Cases
----------

**Non-Existent File**:

.. code-block:: python

   canary_pyt.directives.artifact("missing.txt")  # Warning if file not created

**Empty Pattern**:

.. code-block:: python

   canary_pyt.directives.artifact("*.nonexistent")  # No artifacts saved

**Duplicate Artifacts**:

.. code-block:: python

   canary_pyt.directives.artifact("file.txt")
   canary_pyt.directives.artifact("file.txt")  # Redundant

Notes
-----

- Artifacts are saved from the working directory
- Supports glob patterns for multiple files
- ``save_on`` controls when artifacts are saved:
  - ``always``: Save regardless of outcome
  - ``success``: Save only on success
  - ``failure``: Save only on failure
- Artifacts are preserved in the result directory
- Large artifacts may impact storage

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

Best Practices
--------------

1. **Output Files**:

   .. code-block:: python

      canary_pyt.directives.artifact("result.txt")

2. **Log Files**:

   .. code-block:: python

      canary_pyt.directives.artifact("*.log")

3. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.artifact("debug.txt", when="-o debug")

4. **Save on Failure**:

   .. code-block:: python

      canary_pyt.directives.artifact("error.log", save_on="failure")

5. **Document Purpose**:

   .. code-block:: python

      # Save test output for analysis
      canary_pyt.directives.artifact("output.csv")

See Also
--------

- :doc:`baseline`: Baseline directive
- :doc:`copy`: Copy directive
- :doc:`link`: Link directive
- :doc:`../artifacts`: Artifacts overview
