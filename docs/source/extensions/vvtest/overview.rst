.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Overview
========

The ``canary_vvtest`` extension enables Canary to consume and execute VVTest-style ``.vvt`` files. This provides a migration path for existing VVTest users and allows legacy test suites to run under Canary's modern execution framework.

Historical Context
------------------

VVTest was one of the inspirations for Canary. While Canary has evolved into a general-purpose workflow execution framework, it retains compatibility with VVTest through the ``canary_vvtest`` extension. This allows organizations with existing VVTest investments to:

- Run legacy test suites under Canary
- Migrate incrementally to Canary's native formats
- Leverage Canary's advanced features (resource management, distributed execution, reporting)
- Maintain continuity during transition

Relationship to Canary
----------------------

``canary_vvtest`` is an **extension package**, not part of Canary core:

- It registers as a job generator during Canary initialization
- It discovers ``.vvt`` files and converts them to Canary job specifications
- Canary core performs selection, dependency resolution, resource-aware execution, persistence, and reporting
- The extension does not modify Canary's core architecture

Key Characteristics
-------------------

1. **Compatibility Layer**:
   - Interprets VVTest-style directives (``#VVT:``)
   - Converts to Canary's internal job representation
   - Preserves VVTest semantics where possible

2. **Migration Bridge**:
   - Enables incremental adoption of Canary
   - Allows mixed ``.vvt`` and ``.pyt`` workflows
   - Provides path to modern Canary features

3. **Not Universal**:
   - ``.vvt`` is a compatibility format, not the universal Canary job format
   - Native Python ``.pyt`` files are the reference format
   - VVTest compatibility has limitations (see :doc:`vvtest-limitations`)

When to Use canary_vvtest
--------------------------

Use ``canary_vvtest`` when you need to:

- Run existing VVTest test suites
- Migrate legacy tests incrementally
- Maintain compatibility with VVTest workflows
- Leverage Canary features for VVTest tests

Use ``canary_pyt`` when you:

- Create new test suites
- Want full access to Canary's features
- Prefer Python-based test definitions
- Need maximum flexibility and maintainability

Implementation Model
--------------------

``canary_vvtest`` follows a conversion model:

1. **Discovery**: Scan for ``.vvt`` files
2. **Parsing**: Extract ``#VVT:`` directives
3. **Conversion**: Transform to Canary job specifications
4. **Execution**: Canary core runs the jobs

The extension does not:

- Modify VVTest's behavior
- Reimplement VVTest's execution engine
- Replace Canary's generator architecture

Example: Simple .vvt File
--------------------------

.. code-block:: text

   #VVT: keywords : smoke unit
   #VVT: timeout : 30

   def test():
       assert True

This ``.vvt`` file is discovered by ``canary_vvtest``, converted to a Canary job specification, and executed by Canary core.

See Also
--------

- :doc:`file-format`: VVTest file format details
- :doc:`vvtest-directives`: Supported VVTest directives
- :doc:`../pyt/overview`: Python job-definition reference
- :doc:`legacy-and-migration`: Migration guidance
