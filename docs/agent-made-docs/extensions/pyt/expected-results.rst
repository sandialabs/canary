.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Expected Results
================

Expected results directives specify non-success outcomes that are anticipated and acceptable. These directives enable testing of known issues and expected failures.

xfail Directive
---------------

Mark a test as expected to fail:

.. code-block:: python

   canary_pyt.directives.xfail()
   canary_pyt.directives.xfail(code=1)

**Parameters**:

- **code**: Expected exit code (int, default: -1 for any failure)
- **when**: Conditional activation (WhenType)

**Behavior**:

- Test failure with matching code: ``XFAIL`` (expected failure)
- Test success: ``XPASS`` (unexpected pass)
- Test failure with different code: ``FAILED``

**Exit Codes**:

- ``code=-1``: Any non-zero exit code
- ``code=1``: Specific exit code 1
- ``code=0``: Expect success (unusual)

xdiff Directive
---------------

Mark a test as expected to produce differences:

.. code-block:: python

   canary_pyt.directives.xdiff()

**Parameters**:

- **when**: Conditional activation (WhenType)

**Behavior**:

- Differences from baseline: Expected (test passes)
- No differences: ``XPASS`` (unexpected pass)
- Used with ``baseline`` directive

Expected Exit Code
------------------

Specify expected exit code:

.. code-block:: python

   canary_pyt.directives.xfail(code=1)

**Behavior**:

- Exit code 1: ``XFAIL``
- Exit code 0: ``XPASS``
- Exit code 2: ``FAILED``

Unexpected Pass
---------------

When expected failure/diff does not occur:

**XPASS**:
   - Test passes unexpectedly
   - Often indicates test needs update
   - May reveal fixed issues

.. code-block:: python

   canary_pyt.directives.xfail()  # Test passes → XPASS

Status Outcomes
---------------

**XFAIL**:
   - Expected failure occurred
   - Test behavior is correct
   - No action needed

**XPASS**:
   - Unexpected pass occurred
   - Test or code may have changed
   - Review and update expected result

**PASSED**:
   - Test passed as expected
   - Normal success

Example: Running Tests with Expected Results
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary run ./xstatus, python3 -m canary status -rA]
   :cwd: /examples
   :returncode: [8, 0]

This example demonstrates running tests with expected failure (xfail) and expected difference (xdiff) directives.

**FAILED**:
   - Test failed unexpectedly
   - Investigation needed

Examples
--------

**Expected Failure**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.xfail()

**Expected Failure with Code**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.xfail(code=1)

**Expected Differences**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.baseline("output.txt")
   canary_pyt.directives.xdiff()

**Conditional Expected Failure**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.xfail(code=1, when="platform=windows")

**Platform-Specific Expected Failure**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.xfail(when="platform=windows")

Python Exceptions
-----------------

Use Python exceptions for expected results:

.. code-block:: python

   import canary

   def main():
       if condition:
           raise canary.TestFailed("Expected failure")

**Exception Types**:

- ``canary.TestFailed``: Expected failure
- ``canary.TestDiffed``: Expected difference
- ``canary.TestSkipped``: Expected skip

Best Practices
--------------

1. **Specific Exit Codes**:

   .. code-block:: python

      canary_pyt.directives.xfail(code=1)

2. **Platform-Specific**:

   .. code-block:: python

      canary_pyt.directives.xfail(when="platform=windows")

3. **Conditional Activation**:

   .. code-block:: python

      canary_pyt.directives.xfail(when="-o known_bug")

4. **Document Known Issues**:

   .. code-block:: python

      # Known issue: https://github.com/example/issue/123
      canary_pyt.directives.xfail(code=1)

5. **With Baselines**:

   .. code-block:: python

      canary_pyt.directives.baseline("output.txt")
      canary_pyt.directives.xdiff(when="platform=windows")

See Also
--------

- :doc:`directive-reference/xfail`: Expected failure directive
- :doc:`directive-reference/xdiff`: Expected difference directive
- :doc:`baselines`: Baselines overview
