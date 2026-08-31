.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

stages
======

.. currentmodule:: canary_pyt.directives

.. autofunction:: stages

Purpose
-------

Define test stages or phases. This directive is used to specify the stages that a test goes through during execution.

Parameters
----------

:param \*args: Stage names (string)

Effect on Generated Jobs
------------------------

- Defines test stages
- Stages are recorded in job metadata
- Used for test organization and reporting
- Multiple stages can be specified

When
----

- **Affects**: Generation phase
- **Runtime**: N/A

Examples
--------

**Single Stage**:

.. code-block:: python

   canary_pyt.directives.stages("setup")

**Multiple Stages**:

.. code-block:: python

   canary_pyt.directives.stages("setup", "execute", "teardown")

**Test Lifecycle**:

.. code-block:: python

   canary_pyt.directives.stages("initialize", "run", "validate", "cleanup")

Edge Cases
----------

**No Stages**:

.. code-block:: python

   canary_pyt.directives.stages()  # No stages defined

**Empty Stage**:

.. code-block:: python

   canary_pyt.directives.stages("")  # Empty stage name

Notes
-----

- Stages are used for test organization
- Multiple stages can be specified
- Stages appear in job metadata
- Use for complex test workflows

Best Practices
--------------

1. **Descriptive Stages**:

   .. code-block:: python

      canary_pyt.directives.stages("setup", "execute", "verify")

2. **Test Lifecycle**:

   .. code-block:: python

      canary_pyt.directives.stages("init", "run", "cleanup")

See Also
--------

- :doc:`keywords`: Keywords directive
- :doc:`testname`: Test name directive
