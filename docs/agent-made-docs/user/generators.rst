.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Job Generators
==============

What Job Generators Do
----------------------

Job generators are plugins that bridge user-facing job definitions with Canary's internal job representation. They perform the following key functions:

1. **Discovery**: Scan files and directories to find job definitions
2. **Parsing**: Interpret job specifications in their native format
3. **Validation**: Check job definitions for correctness and completeness
4. **Conversion**: Emit ``JobSpecIR`` or ``JobSpec`` objects for Canary core
5. **Metadata**: Provide additional information about the jobs

Generators enable Canary to support diverse input formats while maintaining a consistent internal processing model.

What Canary Core Expects
-------------------------

Canary core expects generators to:

- **Implement the generator interface**: Follow the ``AbstractSpecGenerator`` contract
- **Emit standardized objects**: Produce ``JobSpecIR`` or ``JobSpec`` objects
- **Handle their own format**: Parse and validate their specific input format
- **Provide metadata**: Include job identity, dependencies, and resource requirements
- **Be discoverable**: Register themselves with Canary's plugin system

Generators must not modify Canary's core execution model; they provide input format support while delegating execution to the core framework.

Why There Is No Universal Input Format
--------------------------------------

Canary intentionally does not define a universal job-definition file format because:

1. **Flexibility**: Different domains have different requirements for job specification
2. **Integration**: Existing tools and workflows use established formats
3. **Extensibility**: New formats can be added without changing core functionality
4. **Specialization**: Format-specific features can be preserved
5. **Evolution**: The ecosystem can adapt to new requirements

This design allows Canary to integrate with existing workflows while providing a consistent execution framework.

Generator Discovery
-------------------

Canary discovers generators through its plugin system:

1. **Entry Point Registration**: Generators register entry points in their ``pyproject.toml``
2. **Plugin Loading**: Canary loads registered generators during initialization
3. **File Association**: Generators declare which file extensions they handle
4. **Discovery Phase**: Canary scans directories and delegates files to appropriate generators

This automatic discovery enables seamless integration of new generators without configuration changes.

Generator Extensions
--------------------

Canary provides several built-in generator extensions:

canary_pyt
~~~~~~~~~~

A **Python job-definition generator** that serves as a reference implementation for extension authors.

- **File Format**: ``.pyt`` files (Python source with directives)
- **Approach**: Uses Python function calls to define test behavior
- **Status**: Extension, not part of Canary core
- **Documentation**: See extension documentation for details

canary_cmake
~~~~~~~~~~~~

A **CTest integration generator** that consumes CMake/CTest test definitions.

- **File Format**: CMakeLists.txt and CTest test definitions
- **Approach**: Integrates with CMake's testing infrastructure
- **Status**: Full integration with CMake/CTest workflows
- **Documentation**: :doc:`../extensions/cmake/index`

canary_vvtest
~~~~~~~~~~~~~

A **VVTest compatibility generator** that supports legacy VVTest file formats.

- **File Format**: ``.vvt`` files (VVTest directive format)
- **Approach**: Provides compatibility with existing VVTest workflows
- **Status**: Compatibility layer, not the primary format
- **Documentation**: :doc:`../extensions/vvtest/index`

Extension-Author View
---------------------

For extension authors, generators provide a clear interface:

1. **Input**: Receive file paths and discovery context
2. **Processing**: Parse files and extract job specifications
3. **Output**: Emit ``JobSpecIR`` or ``JobSpec`` objects
4. **Integration**: Register with Canary's plugin system

The generator interface is designed to be simple and flexible, allowing authors to focus on their specific format requirements while leveraging Canary's execution capabilities.

Generator Development Pattern
------------------------------

To create a new generator:

1. **Implement the interface**: Subclass ``AbstractSpecGenerator``
2. **Handle file discovery**: Declare supported file extensions
3. **Parse input format**: Implement format-specific parsing logic
4. **Emit job specifications**: Create ``JobSpecIR`` or ``JobSpec`` objects
5. **Register the plugin**: Add entry points to ``pyproject.toml``
6. **Test integration**: Verify discovery and execution workflow

This pattern ensures consistency while allowing format-specific customization.

Generator Best Practices
------------------------

Effective generators follow these best practices:

- **Clear documentation**: Explain the input format and its capabilities
- **Comprehensive validation**: Catch errors early in the discovery phase
- **Meaningful metadata**: Provide useful job identity and description
- **Resource awareness**: Specify realistic resource requirements
- **Dependency clarity**: Make job relationships explicit
- **Error handling**: Provide helpful error messages for invalid inputs

These practices ensure generators integrate smoothly with Canary's execution framework.