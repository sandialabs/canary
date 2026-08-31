.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

owners
======

.. currentmodule:: canary_pyt.directives

.. autofunction:: owners

Purpose
-------

Specify test owners for responsibility tracking. Owners are used to identify who is responsible for test maintenance and failures.

Parameters
----------

:param \*args: Owner names (string)

Effect on Generated Jobs
------------------------

- Adds owner metadata to jobs
- Owners are listed in job information
- Used for responsibility tracking and notifications
- Multiple owners can be specified

When
----

- **Affects**: Generation phase
- **Runtime**: N/A

Examples
--------

**Single Owner**:

.. code-block:: python

   canary_pyt.directives.owners("alice")

**Multiple Owners**:

.. code-block:: python

   canary_pyt.directives.owners("alice", "bob", "charlie")

**Team Ownership**:

.. code-block:: python

   canary_pyt.directives.owners("team-performance")

Edge Cases
----------

**No Owners**:

.. code-block:: python

   canary_pyt.directives.owners()  # No owners specified

**Empty Owner**:

.. code-block:: python

   canary_pyt.directives.owners("")  # Empty owner

**Duplicate Owners**:

.. code-block:: python

   canary_pyt.directives.owners("alice", "alice")  # Duplicate

Notes
-----

- Owners are used for responsibility tracking
- Multiple owners can be specified
- Owner names are case-sensitive
- Use team names for shared ownership
- Owners appear in job metadata and reports

Best Practices
--------------

1. **Individual Owners**:

   .. code-block:: python

      canary_pyt.directives.owners("alice")

2. **Team Owners**:

   .. code-block:: python

      canary_pyt.directives.owners("performance-team")

3. **Multiple Owners**:

   .. code-block:: python

      canary_pyt.directives.owners("alice", "bob")

See Also
--------

- :doc:`keywords`: Keywords directive
- :doc:`testname`: Test name directive
