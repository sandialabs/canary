.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

timeout
=======

.. currentmodule:: canary_pyt.directives

.. autofunction:: timeout

Purpose
-------

Set the maximum execution time for a test. If the test exceeds this time, it is terminated and marked as failed.

Parameters
----------

:param arg: Timeout value (int, float, or string)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Sets maximum execution time for the job
- Timeout is enforced by the execution backend
- Timeout exceeded results in job failure
- Accessible via ``instance.timeout`` at runtime

When
----

- **Affects**: Generation phase
- **Runtime**: Timeout enforcement during execution

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.timeout(
       120,
       when="keywords=extended"
   )

Examples
--------

**Integer Timeout (seconds)**:

.. code-block:: python

   canary_pyt.directives.timeout(60)  # 60 seconds

**Float Timeout (seconds)**:

.. code-block:: python

   canary_pyt.directives.timeout(2.5)  # 2.5 seconds

**String Timeout**:

.. code-block:: python

   canary_pyt.directives.timeout("5m")  # 5 minutes
   canary_pyt.directives.timeout("2h")  # 2 hours
   canary_pyt.directives.timeout("30s")  # 30 seconds

**Conditional Timeout**:

.. code-block:: python

   canary_pyt.directives.timeout(
       300,
       when="-o extended"
   )

**Multiple Timeouts**:

.. code-block:: python

   canary_pyt.directives.timeout(60)  # Default timeout
   canary_pyt.directives.timeout(300, when="keywords=slow")  # Extended timeout

Edge Cases
----------

**Zero Timeout**:

.. code-block:: python

   canary_pyt.directives.timeout(0)  # Immediate timeout (not recommended)

**Negative Timeout**:

.. code-block:: python

   canary_pyt.directives.timeout(-1)  # Error: Invalid timeout

**Very Large Timeout**:

.. code-block:: python

   canary_pyt.directives.timeout(86400)  # 24 hours - may be too long

**Timeout Override**:

.. code-block:: python

   canary_pyt.directives.timeout(60)
   canary_pyt.directives.timeout(120)  # Overrides to 120 seconds

Notes
-----

- Timeout values are in seconds unless string format is used
- String format supports: ``s`` (seconds), ``m`` (minutes), ``h`` (hours)
- Timeout is enforced by the execution backend (local, HPC, distributed)
- Timeout does not include setup/cleanup time
- Access timeout at runtime via ``canary.get_instance().timeout``

Runtime Access
--------------

.. code-block:: python

   def main():
       instance = canary.get_instance()
       remaining = instance.timeout - instance.runtime
       print(f"Remaining time: {remaining}s")

See Also
--------

- :doc:`../expected-results`: Expected results overview
- :doc:`xfail`: Expected failure directive
- :doc:`xdiff`: Expected difference directive
