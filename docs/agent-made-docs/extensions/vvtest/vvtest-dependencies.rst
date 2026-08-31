.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

VVTest Dependencies
===================

Dependencies in VVTest define relationships between tests. The ``depends on`` directive specifies that one test depends on another.

depends on / depends_on
-----------------------

### Syntax

.. code-block:: text

   #VVT: depends on : test_name
   #VVT: depends on (expect=1, result=pass) : test_name

### Command Normalization

Command words are joined with underscores:

.. code-block:: text

   #VVT: depends on : setup_test  # Normalized to depends_on

### expect Option

Controls the number of expected dependencies:

.. code-block:: text

   #VVT: depends on (expect=3) : setup_*

### result Option

Maps to Canary result values:

- ``pass`` → ``success``
- ``diff`` → ``diffed``
- ``fail`` → ``failed``
- ``skip`` → ``skipped``

**Example**:

.. code-block:: text

   #VVT: depends on (result=pass) : setup_test

### Dependency Selector Pattern

Supports pattern matching:

.. code-block:: text

   #VVT: depends on : setup_*

### Lower-Casing

The ``when`` option is lower-cased:

.. code-block:: text

   #VVT: depends on (when="platform=linux") : test_name

### Canary Result-Sensitive Behavior

Dependencies are resolved by Canary's dependency system:

- Jobs run in topological order
- Parent jobs wait for dependencies
- Failed dependencies block dependent jobs

### Blocked Jobs

When dependencies fail:

- Dependent jobs are marked as ``BLOCKED``
- Status reflects the dependency failure
- Jobs do not execute

### Migration Implications

VVTest dependencies may differ from Canary:

- Exact ordering semantics may vary
- Result mapping ensures compatibility
- Dependency graphs are validated

Examples
--------

### Simple Dependency

.. code-block:: text

   #VVT: depends on : setup_database

### Conditional Dependency

.. code-block:: text

   #VVT: depends on (when="platform=linux") : setup_linux

### Result-Sensitive Dependency

.. code-block:: text

   #VVT: depends on (expect=1, result=pass) : setup_test

### Pattern Matching

.. code-block:: text

   #VVT: depends on : setup_*

### Multiple Dependencies

.. code-block:: text

   #VVT: depends on : test1
   #VVT: depends on : test2

Best Practices
--------------

1. **Explicit Dependencies**:

   .. code-block:: text

      #VVT: depends on : setup_database

2. **Result-Sensitive**:

   .. code-block:: text

      #VVT: depends on (result=pass) : setup_test

3. **Conditional**:

   .. code-block:: text

      #VVT: depends on (when="-o extended") : extended_setup

4. **Pattern Matching**:

   .. code-block:: text

      #VVT: depends on : setup_*

See Also
--------

- :doc:`vvtest-directives`: Complete directive reference
- :doc:`file-format`: File format details
