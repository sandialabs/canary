.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

include
=======

.. currentmodule:: canary_pyt.directives

.. autofunction:: include

Purpose
-------

Include another file in the current test. This directive is used to incorporate content from other files into the test.

Parameters
----------

:param file: File to include (string)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Includes file content in test
- Effect depends on backend and file type
- Used for modular test construction

When
----

- **Affects**: Generation phase
- **Runtime**: File inclusion during setup

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.include(
       "common.pyt",
       when="-o include"
   )

Examples
--------

**Include Test File**:

.. code-block:: python

   canary_pyt.directives.include("common_tests.pyt")

**Include Data File**:

.. code-block:: python

   canary_pyt.directives.include("test_data.txt")

Edge Cases
----------

**Non-Existent File**:

.. code-block:: python

   canary_pyt.directives.include("missing.pyt")  # Error

**Empty File**:

.. code-block:: python

   canary_pyt.directives.include("")  # Error

Notes
-----

- Include behavior is backend-specific
- Effect depends on file type and content
- Use for modular test construction
- Included files are processed during discovery

See Also
--------

- :doc:`sources`: Sources directive
- :doc:`copy`: Copy directive
- :doc:`link`: Link directive
