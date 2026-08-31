.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

baseline
========

.. currentmodule:: canary_pyt.directives

.. autofunction:: baseline

Purpose
-------

Declare baseline files for comparison. Baselines are reference files used to compare against test output to detect regressions or changes.

Parameters
----------

:param \*args: Baseline specifications (string or dict)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Records baseline specifications
- Baselines are compared during analysis
- Differences are reported
- Supports copy-based and flag-based baselines

When
----

- **Affects**: Generation phase (baseline recording)
- **Runtime**: Baseline comparison during analysis

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.baseline("output.txt", when="-o compare")

Examples
--------

**Copy-Based Baseline**:

.. code-block:: python

   canary_pyt.directives.baseline("output.txt")

**Multiple Baselines**:

.. code-block:: python

   canary_pyt.directives.baseline("file1.txt", "file2.txt")

**Dictionary Form**:

.. code-block:: python

   canary_pyt.directives.baseline({
       "src": "output.txt",
       "dst": "baseline.txt"
   })

**Conditional Baseline**:

.. code-block:: python

   canary_pyt.directives.baseline("result.txt", when="-o extended")

**With Options**:

.. code-block:: python

   canary_pyt.directives.baseline("output.txt", options="ignore_whitespace")

Edge Cases
----------

**Non-Existent File**:

.. code-block:: python

   canary_pyt.directives.baseline("missing.txt")  # Warning/Error

**Empty Baseline**:

.. code-block:: python

   canary_pyt.directives.baseline("")  # Error

**Duplicate Baselines**:

.. code-block:: python

   canary_pyt.directives.baseline("file.txt")
   canary_pyt.directives.baseline("file.txt")  # Redundant

Notes
-----

- Baselines are compared against current output
- Copy-based baselines copy reference files to workspace
- Flag-based baselines use command-line flags
- Baseline differences can be marked as expected with ``xdiff``
- Baselines are stored in the baseline directory
- Use ``canary rebaseline`` to update baselines

Baseline Types
--------------

**Copy-Based**:

.. code-block:: python

   canary_pyt.directives.baseline("output.txt")
   # Copies baseline/output.txt to workspace

**Flag-Based**:

.. code-block:: python

   canary_pyt.directives.baseline("--baseline output.txt")
   # Uses flag to specify baseline

Comparison Workflow
-------------------

1. Test executes and generates output
2. Output is compared against baseline
3. Differences are detected
4. Results are reported
5. Use ``xdiff`` to mark expected differences

Best Practices
--------------

1. **Reference Output**:

   .. code-block:: python

      canary_pyt.directives.baseline("expected_output.txt")

2. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.baseline("result.txt", when="-o compare")

3. **With xdiff**:

   .. code-block:: python

      canary_pyt.directives.baseline("output.txt")
      canary_pyt.directives.xdiff(when="platform=windows")

4. **Document Purpose**:

   .. code-block:: python

      # Reference output for regression detection
      canary_pyt.directives.baseline("result.txt")

See Also
--------

- :doc:`xdiff`: Expected difference directive
- :doc:`artifact`: Artifact directive
- :doc:`../baselines`: Baselines overview
