.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Baselines
=========

Baselines are reference files used to compare against test output to detect regressions or changes. Baselines enable automated regression testing.

baseline Directive
------------------

The ``baseline`` directive declares baseline files:

.. code-block:: python

   canary_pyt.directives.baseline("output.txt")
   canary_pyt.directives.baseline({"src": "output.txt", "dst": "baseline.txt"})

Copy-Based Baselines
--------------------

Copy-based baselines copy reference files to the workspace:

.. code-block:: python

   canary_pyt.directives.baseline("output.txt")

**Behavior**:

- Copies ``baseline/output.txt`` to workspace
- Test output is compared against copied baseline
- Differences are detected and reported

Flag-Based Baselines
--------------------

Flag-based baselines use command-line flags:

.. code-block:: python

   canary_pyt.directives.baseline("--baseline output.txt")

**Behavior**:

- Passes ``--baseline output.txt`` to test script
- Test script handles baseline comparison
- Useful for complex comparison logic

Baseline Actions
----------------

Baselines support different actions:

**copy**:
   Copy baseline file to workspace

.. code-block:: python

   canary_pyt.directives.baseline("output.txt")

**flag**:
   Pass baseline flag to test script

.. code-block:: python

   canary_pyt.directives.baseline("--baseline output.txt")

**script**:
   Use baseline script for comparison

.. code-block:: python

   canary_pyt.directives.baseline("--compare output.txt")

Rebaseline Workflow
-------------------

To update baselines:

1. Run tests with current baselines
2. Review differences
3. Update baselines using ``canary rebaseline``
4. Commit updated baselines

.. code-block:: console

   # Run tests
   python3 -m canary run tests/

   # Review differences
   python3 -m canary status -rA

   # Rebaseline
   python3 -m canary rebaseline tests/

   # Verify
   python3 -m canary run tests/

Baseline Comparison
-------------------

Baseline comparison workflow:

1. Test executes and generates output
2. Output is compared against baseline
3. Differences are detected
4. Results are reported
5. Use ``xdiff`` to mark expected differences

Expected Differences
--------------------

Use ``xdiff`` to mark expected differences:

.. code-block:: python

   canary_pyt.directives.baseline("output.txt")
   canary_pyt.directives.xdiff(when="platform=windows")

**Behavior**:

- Differences on Windows are expected
- Test passes despite differences
- Unexpected differences cause test failure

Examples
--------

**Copy-Based Baseline**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.baseline("output.txt")

**Multiple Baselines**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.baseline("file1.txt", "file2.txt")

**Dictionary Form**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.baseline({
       "src": "output.txt",
       "dst": "baseline.txt"
   })

**Conditional Baseline**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.baseline("result.txt", when="-o compare")

**With Options**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.baseline("output.txt", options="ignore_whitespace")

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

Limitations and Diagnostics
---------------------------

**Missing Baseline**:
   Warning if baseline file does not exist

**Empty Baseline**:
   Warning if baseline file is empty

**No Differences**:
   Test passes if output matches baseline

**Unexpected Differences**:
   Test fails if output differs from baseline

**Expected Differences**:
   Test passes if ``xdiff`` is set

See Also
--------

- :doc:`directive-reference/baseline`: Baseline directive
- :doc:`directive-reference/xdiff`: Expected difference directive
- :doc:`expected-results`: Expected results overview
