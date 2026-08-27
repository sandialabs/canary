.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Overview
========

The ``canary_vvtest`` extension enables Canary to consume and execute VVTest-style ``.vvt`` files.

Relationship to VVTest
=======================

VVTest was one of the inspirations for Canary. The ``canary_vvtest`` extension provides compatibility between the two systems, allowing organizations to:

- Run VVTest test suites using Canary's execution framework
- Leverage Canary's advanced features (resource management, distributed execution, reporting)
- Use both VVTest and Python test formats as needed

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

2. **Dual Format Support**:
    - Allows mixed ``.vvt`` and ``.pyt`` workflows
    - Enables use of both formats based on project needs
    - Provides access to Canary's features for VVTest files

3. **Format Characteristics**:
    - ``.vvt`` files use VVTest's format and semantics
    - ``.pyt`` files use Python-based definitions
    - Both formats are fully supported by Canary

VVTest File Format
==================

The ``canary_vvtest`` extension supports VVTest's file format and execution model:

- Executable scripts with ``.vvt`` extension
- VVTest-specific directives and syntax
- Compatibility with existing VVTest workflows
- Integration with Canary's execution framework
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
- :doc:`vvtest-limitations`: Format limitations and considerations

The ``canary_vvtest`` extension allows running test files formatted for Sandia's `vvtest <https://github.com/sandialabs/vvtest>`_ test harness.
