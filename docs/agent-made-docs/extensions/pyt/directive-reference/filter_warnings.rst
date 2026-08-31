.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

filter_warnings
===============

.. currentmodule:: canary_pyt.directives

.. autofunction:: filter_warnings

Purpose
-------

Control warning filtering for the test. This directive enables or disables warning filtering during test execution.

Parameters
----------

:param arg: Boolean to enable/disable filtering (bool)

Effect on Generated Jobs
------------------------

- Controls warning filtering
- ``True`` enables warning filtering
- ``False`` disables warning filtering
- Affects warning reporting

When
----

- **Affects**: Generation phase
- **Runtime**: Warning filtering during execution

Examples
--------

**Enable Warning Filtering**:

.. code-block:: python

   canary_pyt.directives.filter_warnings(True)

**Disable Warning Filtering**:

.. code-block:: python

   canary_pyt.directives.filter_warnings(False)

Edge Cases
----------

**No Argument**:

.. code-block:: python

   canary_pyt.directives.filter_warnings()  # Error

Notes
-----

- Warning filtering controls warning reporting
- Does not affect test outcome
- Use to reduce noise in test output
- Filtering behavior is backend-specific

See Also
--------

- Python warnings documentation
