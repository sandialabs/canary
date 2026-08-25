.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

set_id
======

.. currentmodule:: canary_pyt.directives

.. autofunction:: set_id

Purpose
-------

Set an explicit ID for the job. IDs are used for unique identification and must follow specific format requirements.

Parameters
----------

:param id: Job ID (string)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Sets explicit job ID
- Overrides generated ID
- Must be unique across test suite
- Used for job identification and tracking

When
----

- **Affects**: Generation phase
- **Runtime**: N/A

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.set_id("custom_id", when="-o custom")

Examples
--------

**Simple ID**:

.. code-block:: python

   canary_pyt.directives.set_id("test_001")

**SHA-like ID**:

.. code-block:: python

   canary_pyt.directives.set_id("abc123def456")

**Parameter-Based ID**:

.. code-block:: python

   canary_pyt.directives.parameterize("config", ["a", "b"])
   canary_pyt.directives.set_id("test_{config}")

Edge Cases
----------

**Empty ID**:

.. code-block:: python

   canary_pyt.directives.set_id("")  # Error: Empty ID

**Duplicate ID**:

.. code-block:: python

   # Two jobs with same ID
   canary_pyt.directives.set_id("duplicate")  # Error: Duplicate

**Invalid Format**:

.. code-block:: python

   canary_pyt.directives.set_id("invalid id")  # Error: Invalid format

Notes
-----

- IDs must be unique
- IDs should follow SHA-like format
- IDs are used for job tracking
- Overrides automatically generated IDs
- IDs appear in reports and status

Best Practices
--------------

1. **Unique IDs**:

   .. code-block:: python

      canary_pyt.directives.set_id("test_001")

2. **SHA-like Format**:

   .. code-block:: python

      canary_pyt.directives.set_id("a1b2c3d4")

3. **Parameter-Based**:

   .. code-block:: python

      canary_pyt.directives.set_id("test_{param}")

See Also
--------

- :doc:`testname`: Test name directive
- :doc:`parameterize`: Parameterization directive
