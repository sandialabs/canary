.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

xdiff
=====

.. currentmodule:: canary_pyt.directives

.. autofunction:: xdiff

Purpose
-------

Mark a test as expected to produce differences. Used for tests that compare output against baselines and expect differences.

Parameters
----------

:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Marks job as expected to have differences
- Differences are reported but don't fail the test
- Used with baseline comparison tests
- Accessible via ``instance.xdiff`` at runtime

When
----

- **Affects**: Generation phase (expectation setting)
- **Runtime**: Difference checking during execution

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.xdiff(when="platform=windows")

Examples
--------

**Unconditional Expected Difference**:

.. code-block:: python

   canary_pyt.directives.xdiff()  # Expects differences

**Conditional Expected Difference**:

.. code-block:: python

   canary_pyt.directives.xdiff(when="platform=windows")

**With Baseline**:

.. code-block:: python

   canary_pyt.directives.baseline("output.txt")
   canary_pyt.directives.xdiff()  # Expect differences from baseline

Edge Cases
----------

**No Baseline**:

.. code-block:: python

   canary_pyt.directives.xdiff()  # Warning: No baseline specified

**Multiple xdiff**:

.. code-block:: python

   canary_pyt.directives.xdiff()
   canary_pyt.directives.xdiff()  # Redundant

Notes
-----

- ``xdiff`` expects differences in baseline comparison
- Used with ``baseline`` directive
- Differences are reported but test passes
- Access xdiff status at runtime via ``canary.get_instance().xdiff``
- Typically used for platform-specific output variations

Comparison with xfail
---------------------

**xdiff**:

.. code-block:: python

   canary_pyt.directives.xdiff()  # Expects differences

**xfail**:

.. code-block:: python

   canary_pyt.directives.xfail()  # Expects failure

Use Cases
---------

**Platform-Specific Output**:

.. code-block:: python

   canary_pyt.directives.baseline("result.txt")
   canary_pyt.directives.xdiff(when="platform=windows")

**Known Output Variations**:

.. code-block:: python

   canary_pyt.directives.baseline("data.csv")
   canary_pyt.directives.xdiff(when="-o allow_variation")

**Temporary Differences**:

.. code-block:: python

   canary_pyt.directives.baseline("output.log")
   canary_pyt.directives.xdiff()  # Mark as expected during transition

Best Practices
--------------

1. **With Baseline**:

   .. code-block:: python

      canary_pyt.directives.baseline("file.txt")
      canary_pyt.directives.xdiff()

2. **Platform-Specific**:

   .. code-block:: python

      canary_pyt.directives.xdiff(when="platform=windows")

3. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.xdiff(when="-o expected_variation")

4. **Document Reason**:

   .. code-block:: python

      # Platform-specific line endings
      canary_pyt.directives.xdiff(when="platform=windows")

See Also
--------

- :doc:`xfail`: Expected failure directive
- :doc:`baseline`: Baseline directive
- :doc:`../expected-results`: Expected results overview
- :doc:`../conditional-activation`: Conditional activation
