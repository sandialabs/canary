.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

skipif
======

.. currentmodule:: canary_pyt.directives

.. autofunction:: skipif

Purpose
-------

Conditionally skip test execution based on a condition. If the condition is true, the job is skipped with a reason.

Parameters
----------

:param arg: Boolean condition (True to skip, False to run)
:param reason: Skip reason (string)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Skips jobs when condition is true
- Skip reason is recorded in job status
- Skipped jobs appear as ``SKIPPED`` in status
- Skip condition is evaluated at runtime

When
----

- **Affects**: Runtime (job execution)
- **Evaluation**: Condition evaluated when job would run

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.skipif(
       True,
       reason="Not applicable",
       when="platform=windows"
   )

Examples
--------

**Unconditional Skip**:

.. code-block:: python

   canary_pyt.directives.skipif(True, reason="Test not applicable")

**Conditional Skip**:

.. code-block:: python

   import sys

   canary_pyt.directives.skipif(
       sys.platform == "win32",
       reason="Windows not supported"
   )

**Platform-Specific Skip**:

.. code-block:: python

   canary_pyt.directives.skipif(
       True,
       reason="Linux only",
       when="platform!=linux"
   )

**Multiple Skip Conditions**:

.. code-block:: python

   canary_pyt.directives.skipif(True, reason="Quick mode", when="-o quick")
   canary_pyt.directives.skipif(True, reason="CI only", when="not ci")

Edge Cases
----------

**No Reason**:

.. code-block:: python

   canary_pyt.directives.skipif(True)  # Error: Requires reason

**Empty Reason**:

.. code-block:: python

   canary_pyt.directives.skipif(True, reason="")  # Warning: Empty reason

**Conflicting Conditions**:

.. code-block:: python

   canary_pyt.directives.skipif(True, reason="A", when="-o quick")
   canary_pyt.directives.skipif(False, reason="B", when="-o quick")  # Overrides

Notes
-----

- ``skipif`` skips jobs at runtime, not generation time
- Skip reason is required and appears in status
- Use ``enable`` for generation-time masking
- Multiple ``skipif`` directives: last one wins
- Skip conditions are evaluated in order
- Skipped jobs don't execute but are counted in totals

Comparison with enable
----------------------

**skipif**:

.. code-block:: python

   canary_pyt.directives.skipif(True, reason="Not needed")
   # Job is skipped at runtime with reason

**enable**:

.. code-block:: python

   canary_pyt.directives.enable(False)
   # Job is masked at generation time

Runtime Behavior
----------------

Skipped jobs show reason:

.. code-block:: console

   $ python3 -m canary run tests/
   test1: SKIPPED (Windows not supported)
   test2: PASSED

Best Practices
--------------

1. **Descriptive Reasons**:

   .. code-block:: python

      canary_pyt.directives.skipif(
          platform == "win32",
          reason="Windows filesystem limitations"
      )

2. **Platform-Specific**:

   .. code-block:: python

      canary_pyt.directives.skipif(
          True,
          reason="Requires Linux",
          when="platform!=linux"
      )

3. **Conditional Activation**:

   .. code-block:: python

      canary_pyt.directives.skipif(
          True,
          reason="Extended tests only",
          when="not -o extended"
      )

See Also
--------

- :doc:`enable`: Enable/disable directive
- :doc:`../conditional-activation`: Conditional activation overview
- :doc:`../execution-model`: Execution model details
