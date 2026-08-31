.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

xfail
=====

.. currentmodule:: canary_pyt.directives

.. autofunction:: xfail

Purpose
-------

Mark a test as expected to fail. If the test fails, it's reported as ``XFAIL`` (expected failure). If it passes, it's reported as ``XPASS`` (unexpected pass).

Parameters
----------

:param code: Expected exit code (int, default: -1 for any failure)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Marks job as expected to fail
- Exit code ``code`` is expected (default: any non-zero)
- Actual failure: reported as ``XFAIL``
- Unexpected pass: reported as ``XPASS``
- Accessible via ``instance.xfail`` at runtime

When
----

- **Affects**: Generation phase (expectation setting)
- **Runtime**: Expectation checked during execution

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.xfail(code=1, when="platform=windows")

Examples
--------

**Unconditional Expected Failure**:

.. code-block:: python

   canary_pyt.directives.xfail()  # Expects any failure

**Specific Exit Code**:

.. code-block:: python

   canary_pyt.directives.xfail(code=1)  # Expects exit code 1

**Conditional Expected Failure**:

.. code-block:: python

   canary_pyt.directives.xfail(code=1, when="platform=windows")

**Multiple Exit Codes**:

.. code-block:: python

   # Use multiple xfail directives for different codes
   canary_pyt.directives.xfail(code=1, when="-o strict")
   canary_pyt.directives.xfail(code=2, when="-o strict")

Edge Cases
----------

**Code 0**:

.. code-block:: python

   canary_pyt.directives.xfail(code=0)  # Expects success (unusual)

**Negative Code**:

.. code-block:: python

   canary_pyt.directives.xfail(code=-1)  # Default: any failure

**Very Large Code**:

.. code-block:: python

   canary_pyt.directives.xfail(code=999)  # Valid but unusual

**Override**:

.. code-block:: python

   canary_pyt.directives.xfail(code=1)
   canary_pyt.directives.xfail(code=2)  # Overrides to code 2

Notes
-----

- ``xfail`` sets expectation for failure
- Default code ``-1`` matches any non-zero exit code
- ``XFAIL``: test failed as expected
- ``XPASS``: test passed unexpectedly (often indicates test needs update)
- Access xfail status at runtime via ``canary.get_instance().xfail``
- Multiple ``xfail`` directives: last one wins

Runtime Access
--------------

.. code-block:: python

   def main():
       instance = canary.get_instance()
       if instance.xfail:
           print(f"Expected to fail with code: {instance.xfail.code}")

Comparison with xdiff
---------------------

**xfail**:

.. code-block:: python

   canary_pyt.directives.xfail()  # Expects failure

**xdiff**:

.. code-block:: python

   canary_pyt.directives.xdiff()  # Expects differences

Status Outcomes
---------------

Possible outcomes:

- ``XFAIL``: Test failed as expected
- ``XPASS``: Test passed unexpectedly
- ``PASSED``: Test passed (if not xfail)
- ``FAILED``: Test failed (if not xfail)

Best Practices
--------------

1. **Specific Exit Codes**:

   .. code-block:: python

      canary_pyt.directives.xfail(code=1)  # Specific expectation

2. **Platform-Specific**:

   .. code-block:: python

      canary_pyt.directives.xfail(
          code=1,
          when="platform=windows"
      )

3. **Conditional Activation**:

   .. code-block:: python

      canary_pyt.directives.xfail(
          code=1,
          when="-o known_bug"
      )

4. **Document Known Issues**:

   .. code-block:: python

      # Known issue: https://github.com/example/issue/123
      canary_pyt.directives.xfail(code=1)

See Also
--------

- :doc:`xdiff`: Expected difference directive
- :doc:`../expected-results`: Expected results overview
- :doc:`../conditional-activation`: Conditional activation
