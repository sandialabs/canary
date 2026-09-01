.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-docs:

Documentation System
====================

Canary's documentation system supports extension documentation through a centralized structure. This guide explains how extension documentation is organized and integrated.

Documentation Organization
---------------------------

Extension documentation follows a structured approach:

**Centralized Structure**:

- Extension docs are part of the main documentation tree
- Located under ``doc/source/extending/``
- Integrated with core user guide and reference

**Extension Documentation Tree**:

.. code-block:: text

   doc/source/
   ├── user/                      # Core user guide
   ├── reference/                # Command reference
   ├── extending/                # Extension authoring guide
   │   ├── index.rst             # Extension guide index
   │   ├── plugins.rst           # Plugin loading and management
   │   ├── hooks.rst             # Comprehensive hook reference
   │   ├── generators.rst        # Job generator development
   │   ├── commands.rst          # Command extension
   │   ├── configuration.rst     # Configuration extensions
   │   ├── resources.rst         # Resource management extensions
   │   ├── reporters.rst         # Reporter extensions
   │   ├── measurements.rst      # Measurement extensions
   │   └── docs.rst              # Documentation system
   └── extensions/               # Extension-specific documentation
       ├── pyt/                   # Python extension docs
       ├── cmake/                 # CMake extension docs
       ├── cdash/                 # CDash extension docs
       ├── hpc/                   # HPC extension docs
       ├── gpu/                   # GPU extension docs
       └── vvtest/                # VVTest extension docs

Extension-Specific Documentation
---------------------------------

Each extension maintains its own documentation:

**Location**: ``doc/source/extensions/<extension-name>/``

**Structure**:

.. code-block:: text

   doc/source/extensions/pyt/
   ├── index.rst                # Extension overview
   ├── installation.rst        # Installation instructions
   ├── usage.rst               # Usage examples
   ├── configuration.rst       # Configuration options
   └── examples/               # Practical examples

**Integration**:

- Extension docs are linked from the main documentation
- Cross-references use standard Sphinx syntax
- Follow Canary's documentation conventions

Command Reference Generation
----------------------------

Canary generates command reference documentation automatically:

**Command Reference Pages**:

- Generated pages are flattened under ``doc/source/reference/commands.<command>.rst``
- Use absolute Sphinx document paths for cross-references

**Reference Examples**:

.. code-block:: rst

   :doc:`/reference/commands.config`
   :doc:`/reference/commands.query`
   :doc:`/reference/commands.run`

**Command Reference Generation**:

Use the ``canary commands`` command to generate reference documentation:

.. code-block:: console

   $ canary commands --help
   $ canary commands list
   $ canary commands generate

Validation Scripts
------------------

Canary provides validation scripts to ensure documentation quality:

**bin/check-docs**:

- Validates documentation structure
- Checks for broken references
- Verifies cross-reference consistency

**bin/check-docs-strict**:

- Strict validation mode
- Enforces documentation standards
- Checks for style consistency

**Usage**:

.. code-block:: console

   $ bin/check-docs
   $ bin/check-docs-strict

Documentation Best Practices
----------------------------

**Structure**:

- Follow existing documentation patterns
- Use consistent heading levels
- Organize content logically

**Cross-References**:

- Use absolute paths for command references
- Verify all cross-references exist
- Prefer explicit references over implicit ones

**Examples**:

- Use concise, realistic examples
- Include both code and console examples
- Test examples before including

**Style**:

- Use technical manual style
- Avoid marketing language
- Be source-grounded and accurate

Documentation Workflow
----------------------

**Drafting Mode**:

1. Inspect relevant source code
2. Review existing documentation patterns
3. Write or update documentation
4. Perform self-review
5. Update ``docs-progress.md``

**Validation Mode**:

1. Run Sphinx documentation build
2. Fix warnings and errors
3. Validate cross-references
4. Test executable examples
5. Update ``docs-progress.md``

Extension Documentation Examples
---------------------------------

**Python Extension Documentation**:

.. code-block:: rst

   .. toctree::
      :maxdepth: 2

      ../extensions/pyt/index
      ../extensions/pyt/installation
      ../extensions/pyt/usage

**CDash Extension Documentation**:

.. code-block:: rst

   .. toctree::
      :maxdepth: 2

      ../extensions/cdash/index
      ../extensions/cdash/configuration
      ../extensions/cdash/examples

Documentation Troubleshooting
-----------------------------

**Broken References**:

- Verify reference paths exist
- Check for typos in reference names
- Ensure target documents are included in toctree

**Build Errors**:

- Check for syntax errors
- Validate cross-reference targets
- Test with different Sphinx versions

**Style Issues**:

- Use ``bin/check-docs-strict`` for validation
- Follow existing documentation patterns
- Review documentation guidelines

See Also
--------

- :doc:`plugins`: Plugin documentation structure
- :doc:`../user/concepts`: Core Canary concepts
- :doc:`/reference/commands`: Command reference
- :doc:`../extensions/pyt/index`: Python extension example