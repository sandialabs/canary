.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

enable
======

.. currentmodule:: canary_pyt.directives

.. autofunction:: enable

Purpose
-------

Conditionally enable or disable test execution. This directive controls whether a job is active based on conditional activation.

Parameters
----------

:param \*args: Boolean values to determine enablement
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Masks jobs based on conditional activation
- ``enable(False)`` or ``enable(True)`` controls job activation
- Jobs marked as disabled are not scheduled or executed
- Disabled jobs appear as ``SKIPPED`` in status

When
----

- **Affects**: Generation phase (job masking)
- **Runtime**: N/A (disabled jobs don't run)

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.enable(False, when="-o quick")

Examples
--------

**Disable Job**:

.. code-block:: python

   canary_pyt.directives.enable(False)  # Job is disabled

**Enable Job**:

.. code-block:: python

   canary_pyt.directives.enable(True)  # Job is enabled (default)

**Conditional Disable**:

.. code-block:: python

   canary_pyt.directives.enable(False, when="-o quick")

**Conditional Enable**:

.. code-block:: python

   canary_pyt.directives.enable(True, when="-o extended")

**Multiple Conditions**:

.. code-block:: python

   canary_pyt.directives.enable(False, when="platform=windows")
   canary_pyt.directives.enable(True, when="platform=linux")

Edge Cases
----------

**No Arguments**:

.. code-block:: python

   canary_pyt.directives.enable()  # Error: Requires at least one argument

**Multiple Boolean Values**:

.. code-block:: python

   canary_pyt.directives.enable(True, False, True)  # Last value wins

**Conflicting Conditions**:

.. code-block:: python

   canary_pyt.directives.enable(False, when="-o quick")
   canary_pyt.directives.enable(True, when="-o quick")  # Overrides to True

Notes
-----

- ``enable`` masks jobs at generation time
- Disabled jobs are not scheduled or executed
- Use ``skipif`` for conditional skipping based on runtime conditions
- ``enable`` is evaluated before job generation
- Disabled jobs appear as ``SKIPPED`` in test status
- Multiple ``enable`` directives: last one wins

Comparison with skipif
----------------------

**enable**:

.. code-block:: python

   canary_pyt.directives.enable(False, when="-o quick")
   # Job is masked at generation time

**skipif**:

.. code-block:: python

   canary_pyt.directives.skipif(True, reason="Not needed")
   # Job is skipped at runtime

Runtime Behavior
----------------

Disabled jobs don't execute:

.. code-block:: console

   $ python3 -m canary run tests/
   test1: SKIPPED (disabled)
   test2: PASSED

See Also
--------

- :doc:`skipif`: Conditional skip directive
- :doc:`../conditional-activation`: Conditional activation overview
- :doc:`../execution-model`: Execution model details
