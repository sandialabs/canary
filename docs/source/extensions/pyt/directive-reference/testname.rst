.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

testname
========

.. currentmodule:: canary_pyt.directives

.. autofunction:: testname

Purpose
-------

Set the test name explicitly. This overrides the default name derived from the file name.

Parameters
----------

:param arg: Test name (string)

Effect on Generated Jobs
------------------------

- Sets the explicit test name
- Overrides default name from file
- Used in job identification and reporting
- Must be unique within the test suite

When
----

- **Affects**: Generation phase
- **Runtime**: N/A

Examples
--------

**Simple Test Name**:

.. code-block:: python

   canary_pyt.directives.testname("my_test")

**Descriptive Test Name**:

.. code-block:: python

   canary_pyt.directives.testname("performance_benchmark")

**Hierarchical Test Name**:

.. code-block:: python

   canary_pyt.directives.testname("unit.tests.math.addition")

Edge Cases
----------

**Empty Name**:

.. code-block:: python

   canary_pyt.directives.testname("")  # Error: Empty name

**Duplicate Name**:

.. code-block:: python

   # Two tests with same name
   canary_pyt.directives.testname("duplicate")  # Error: Duplicate

**Invalid Characters**:

.. code-block:: python

   canary_pyt.directives.testname("test name")  # May cause issues

Notes
-----

- Test names must be unique
- Names should be descriptive
- Avoid special characters and spaces
- Test names appear in reports and status
- Default name is derived from file name if not specified

Best Practices
--------------

1. **Descriptive Names**:

   .. code-block:: python

      canary_pyt.directives.testname("test_addition")

2. **Hierarchical Names**:

   .. code-block:: python

      canary_pyt.directives.testname("math.addition.test")

3. **Component Names**:

   .. code-block:: python

      canary_pyt.directives.testname("database.connection.test")

See Also
--------

- :doc:`set_id`: Set explicit ID directive
- :doc:`keywords`: Keywords directive

Aliases
-------

**name**:

.. code-block:: python

   canary_pyt.directives.name("test")  # Alias for testname

The ``name`` directive is an alias for ``testname`` and behaves identically.
