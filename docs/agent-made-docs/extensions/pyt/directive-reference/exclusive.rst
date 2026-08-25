.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

exclusive
=========

.. currentmodule:: canary_pyt.directives

.. autofunction:: exclusive

Purpose
-------

Mark a job as requiring exclusive resource access. Exclusive jobs run without sharing resources with other jobs.

Parameters
----------

:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Marks job as exclusive
- Job runs with dedicated resources
- No resource sharing with other jobs
- Affects scheduling in resource pool

When
----

- **Affects**: Generation phase
- **Runtime**: Resource allocation during execution

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.exclusive(when="-o exclusive")

Examples
--------

**Unconditional Exclusive**:

.. code-block:: python

   canary_pyt.directives.exclusive()

**Conditional Exclusive**:

.. code-block:: python

   canary_pyt.directives.exclusive(when="keywords=performance")

Edge Cases
----------

**Multiple Exclusive**:

.. code-block:: python

   canary_pyt.directives.exclusive()
   canary_pyt.directives.exclusive()  # Redundant

Notes
-----

- Exclusive jobs have dedicated resources
- Use for performance-sensitive tests
- May reduce resource pool utilization
- Exclusive jobs wait for resources to be available
- Combines with CPU/GPU/node requirements

Best Practices
--------------

1. **Performance Tests**:

   .. code-block:: python

      canary_pyt.directives.exclusive()
      canary_pyt.directives.cpus(8)

2. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.exclusive(when="-o accurate")

3. **Resource-Intensive**:

   .. code-block:: python

      canary_pyt.directives.exclusive()
      canary_pyt.directives.gpus(4)

See Also
--------

- :doc:`cpus`: CPU resource directive
- :doc:`gpus`: GPU resource directive
- :doc:`nodes`: Node resource directive
- :doc:`../resources`: Resource overview
