.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Legacy and Migration
=====================

The ``canary_vvtest`` extension provides a practical migration path for organizations with existing VVTest investments. This page explains how to approach legacy VVTest suites and plan for migration to native Canary formats.

Practical Compatibility
-----------------------

**What Works**:

- ``#VVT:`` directive syntax
- Common directives (keywords, timeout, parameterize, etc.)
- Dependency graphs
- Basic workflow patterns
- Canary's advanced features (resource management, distributed execution)

**What May Differ**:

- Exact dependency semantics
- Resource allocation details
- Timeout handling
- Platform-specific behavior
- Error reporting format

**Not Supported**:

- VVTest-specific runtime environment
- Custom VVTest plugins
- Some advanced VVTest features

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

Compatibility Guidance
----------------------

### What to Expect

**Similar**:

- Test discovery and execution
- Dependency resolution
- Parameterization
- Keyword filtering
- Timeout enforcement

**Different**:

- Job naming conventions
- Resource specification
- Status reporting
- Result persistence
- Query interface

### Testing Legacy Suites

1. **Start Small**:
   - Test a subset of critical tests first
   - Verify behavior matches expectations
   - Address issues before full migration

2. **Validate Results**:
   - Compare outputs between VVTest and Canary
   - Check dependency graphs
   - Verify resource allocation

3. **Incremental Adoption**:
   - Migrate test suites one at a time
   - Use both systems in parallel during transition
   - Monitor for regressions

Examples
--------

### Running Legacy Suite

.. code-block:: console

   # Discover and run .vvt files
   python3 -m canary run tests/legacy/

### Mixed Workflow

.. code-block:: console

   # Run both .vvt and .pyt files
   python3 -m canary run tests/

### Incremental Conversion

.. code-block:: python

   # Convert .vvt to .pyt incrementally
   # Start with simple tests
   # Validate at each step

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

Migration Patterns
------------------

### Direct Conversion

Convert ``.vvt`` directives to ``.pyt`` directives:

**VVTest**:
```text
#VVT: keywords : smoke unit
#VVT: timeout : 30
``````````````````

**Canary**:
```python
import canary_pyt
canary_pyt.directives.keywords("smoke", "unit")
canary_pyt.directives.timeout(30)
`````````````````````````````````

### Dependency Conversion

**VVTest**:
```text
#VVT: depends on : setup_test
`````````````````````````````

**Canary**:
```python
import canary_pyt
canary_pyt.directives.depends_on("setup_test")
``````````````````````````````````````````````

### Parameterization Conversion

**VVTest**:
```text
#VVT: parameterize : size = 10 20 30
````````````````````````````````````

**Canary**:
```python
import canary_pyt
canary_pyt.directives.parameterize("size", [10, 20, 30])
````````````````````````````````````````````````````````

See Also
--------

- :doc:`file-format`: VVTest file format reference
- :doc:`vvtest-directives`: Supported directives
- :doc:`../pyt/overview`: Python job-definition guide
- :doc:`vvtest-compatibility`: Detailed compatibility notes
