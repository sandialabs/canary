.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

VVTest Compatibility and Migration
===================================

This page explains practical compatibility guidance for running VVTest suites under Canary.

What Works
-----------

### Supported Features

- ``#VVT:`` directive syntax
- Common directives (keywords, timeout, parameterize, etc.)
- Dependency graphs
- Basic workflow patterns
- Canary's advanced features (resource management, distributed execution)

### Canary Integration Hooks

The ``canary_vvtest`` extension integrates with Canary through several hooks:

- ``canary_collectstart``: Registers ``VVTestSpecGenerator`` for ``*.vvt`` file discovery
- ``canary_generate_modifyitems``: Sets ``execute.log`` as stdout and handles resource mappings
- ``canary_runteststart``: Writes ``vvtest_util.py`` compatibility module to execution directory
- ``canary_cdash_name``: Provides CDash-compatible test names for ``.vvt`` jobs
- ``canary_addoption``: Adds ``-R`` and ``-a/--analyze`` command-line options

### Compatibility Level

Practical compatibility for:

- Test discovery and execution
- Dependency resolution
- Parameterization
- Keyword filtering
- Timeout enforcement

What May Differ
---------------

### Execution Semantics

- Exact ordering may vary
- Result mapping ensures compatibility
- Dependency graphs are validated

### Resource Handling

- Resource allocation details may differ
- Mapping ensures compatibility (np → cpus, etc.)

### Status Reporting

- Status formats may differ
- Core results (PASSED, FAILED) are preserved

### Query Interface

- Query syntax may differ
- Core filtering works

What Is Not Supported
---------------------

### VVTest-Specific Features

- VVTest runtime environment
- Custom VVTest plugins
- Some advanced VVTest features

### Limitations

- Not all VVTest behaviors are supported
- Parsing is source-specific
- Includes must exist
- Generated parameter scripts require executable tools
- Time formats may differ
- Dependency semantics may differ
- Resource mapping may differ

Testing Legacy Suites
---------------------

### Start Small

1. Test a subset of critical tests first
2. Verify behavior matches expectations
3. Address issues before full migration

### Validate Results

1. Compare outputs between VVTest and Canary
2. Check dependency graphs
3. Verify resource allocation

### Incremental Adoption

1. Migrate test suites one at a time
2. Use both systems in parallel during transition
3. Monitor for regressions

Migration Strategy
------------------

### Phase 1: Run Under Canary

1. Install ``canary_vvtest`` extension
2. Point Canary at existing ``.vvt`` files
3. Verify test execution matches expectations
4. Address compatibility issues

**Benefits**:
- Immediate access to Canary features
- No test suite changes required
- Minimal disruption

### Phase 2: Incremental Migration

1. Identify critical test suites
2. Convert to ``.pyt`` format incrementally
3. Run mixed ``.vvt`` and ``.pyt`` workflows
4. Validate results at each step

**Benefits**:
- Reduced risk
- Gradual learning curve
- Parallel validation

### Phase 3: Full Migration

1. All tests converted to ``.pyt``
2. Remove ``canary_vvtest`` dependency
3. Use native Canary features
4. Maintain as Python-based suite

**Benefits**:
- Full access to Canary ecosystem
- Better maintainability
- Modern Python features
- Community support

Resource Mappings
-----------------

### np → cpus

VVTest ``np`` maps to Canary ``cpus``:

.. code-block:: text

   #VVT: parameterize : np = 1 2 4

### ndevice → gpus

VVTest ``ndevice`` maps to Canary ``gpus``:

.. code-block:: text

   #VVT: parameterize : ndevice = 1 2

### nnode → nodes

VVTest ``nnode`` maps to Canary ``nodes``:

.. code-block:: text

   #VVT: parameterize : nnode = 1 2

Execution Log
-------------

### execute.log

All stdout/stderr combined into ``execute.log``:

.. code-block:: text

   # Output and errors go to execute.log

vvtest_util.py
--------------

### Compatibility Module

Generated at runtime for ``.vvt`` jobs:

.. code-block:: python

   import vvtest_util as vvt

### opt_analyze

Based on ``--execute-analysis-sections``:

.. code-block:: console

   python3 -m canary run -a tests/

### is_analysis_only

Also based on ``--execute-analysis-sections``.

When to Migrate
---------------

### Consider Migration When

- Need full access to Canary features
- Want better maintainability
- Prefer Python-based definitions
- Need maximum flexibility

### Keep VVTest When

- Legacy suites are stable
- Migration effort is high
- VVTest features are sufficient
- Team is familiar with VVTest

Best Practices
--------------

1. **Test Incrementally**:
   - Convert a few tests at a time
   - Validate results before proceeding
   - Address issues early

2. **Leverage Canary Features**:
   - Use Canary's resource management
   - Adopt Canary's reporting
   - Explore Canary's distributed execution

3. **Document Differences**:
   - Track VVTest vs Canary behavior
   - Note limitations and workarounds
   - Update team documentation

4. **Train Team**:
   - Introduce Canary concepts
   - Demonstrate ``.pyt`` format
   - Share migration patterns

Examples
--------

### Mixed Workflow

.. code-block:: console

   # Run both .vvt and .pyt files
   python3 -m canary run tests/

### Incremental Conversion

.. code-block:: python

   # Convert .vvt to .pyt incrementally
   # Start with simple tests
   # Validate at each step

See Also
--------

- :doc:`vvtest-directives`: Complete directive reference
- :doc:`file-format`: File format details
