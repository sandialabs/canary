.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Explicit IDs
============

Explicit IDs provide unique identification for jobs. IDs are used for tracking, reporting, and dependency resolution.

set_id Directive
----------------

Set an explicit ID for a job:

.. code-block:: python

   canary_pyt.directives.set_id("test_001")

**Parameters**:

- **id**: Job ID (string)
- **when**: Conditional activation (WhenType)

SHA-like IDs
------------

IDs should follow SHA-like format:

.. code-block:: python

   canary_pyt.directives.set_id("abc123def456")

**Format**:

- Lowercase hexadecimal characters
- No special characters
- Unique across test suite

Templates
---------

Use parameter substitution in IDs:

.. code-block:: python

   canary_pyt.directives.parameterize("config", ["a", "b"])
   canary_pyt.directives.set_id("test_{config}")

**Behavior**:

- ``config=a``: ID is ``test_a``
- ``config=b``: ID is ``test_b``

Uppercase Parameter Names
--------------------------

Parameter names in templates are case-sensitive:

.. code-block:: python

   canary_pyt.directives.parameterize("CONFIG", ["A", "B"])
   canary_pyt.directives.set_id("test_{CONFIG}")

**Behavior**:

- ``CONFIG=A``: ID is ``test_A``
- ``CONFIG=B``: ID is ``test_B``

Uniqueness Requirement
-----------------------

IDs must be unique:

.. code-block:: python

   # test1.pyt
   canary_pyt.directives.set_id("duplicate")

   # test2.pyt
   canary_pyt.directives.set_id("duplicate")  # Error: Duplicate ID

**Behavior**:

- Duplicate IDs cause errors
- IDs must be unique across test suite
- Generated IDs are unique by default

Composite Parent Behavior
--------------------------

Composite jobs have special ID behavior:

.. code-block:: python

   canary_pyt.directives.aggregate(
       "analyze",
       ["test1", "test2"]
   )

**Behavior**:

- Composite job has its own ID
- Child jobs have their own IDs
- IDs are independent

Errors and Diagnostics
----------------------

**Empty ID**:

.. code-block:: python

   canary_pyt.directives.set_id("")  # Error: Empty ID

**Invalid Format**:

.. code-block:: python

   canary_pyt.directives.set_id("invalid id")  # Error: Invalid format

**Duplicate ID**:

.. code-block:: python

   canary_pyt.directives.set_id("duplicate")  # Error: Duplicate

Examples
--------

**Simple ID**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.set_id("test_001")

**SHA-like ID**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.set_id("a1b2c3d4e5f6")

**Parameter-Based ID**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.parameterize("size", [10, 20, 30])
   canary_pyt.directives.set_id("test_size_{size}")

**Conditional ID**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.set_id("custom_id", when="-o custom")

Best Practices
--------------

1. **Unique IDs**:

   .. code-block:: python

      canary_pyt.directives.set_id("test_001")

2. **SHA-like Format**:

   .. code-block:: python

      canary_pyt.directives.set_id("abc123def")

3. **Parameter-Based**:

   .. code-block:: python

      canary_pyt.directives.set_id("test_{param}")

4. **Descriptive IDs**:

   .. code-block:: python

      canary_pyt.directives.set_id("performance_test")

5. **Conditional IDs**:

   .. code-block:: python

      canary_pyt.directives.set_id("custom", when="-o custom")

See Also
--------

- :doc:`directive-reference/set_id`: Set ID directive
- :doc:`directive-reference/testname`: Test name directive
- :doc:`composite-analysis`: Composite analysis overview
