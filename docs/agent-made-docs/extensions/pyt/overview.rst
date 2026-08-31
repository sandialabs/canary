.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Overview
========

The ``canary_pyt`` extension is a **job generator extension** for Canary that enables Python-based test job definitions. It is the reference implementation for defining Canary jobs programmatically.

Key Characteristics
-------------------

1. **Extension Package**: ``canary_pyt`` is an extension package, not part of Canary core. It registers itself as a job generator during Canary initialization.

2. **Reference Generator**: It is the canonical Python job-definition generator for Canary, demonstrating best practices for extension authors.

3. **Directive-Based**: Uses Python function calls (directives) to define test behavior, resources, and metadata.

4. **File Format**: ``.pyt`` files are Python source files that use ``canary_pyt.directives`` to define test specifications.

5. **Not Universal**: While ``.pyt`` is a primary format, Canary core can consume jobs from any registered generator that emits ``JobSpecIR`` or ``JobSpec`` objects.

Relationship to Canary Core
---------------------------

``canary_pyt`` integrates with Canary through the generator plugin system:

- **Discovery Phase**: ``canary_pyt`` scans ``.pyt`` files and records directives
- **Generation Phase**: Directives are converted to ``JobSpecIR`` objects
- **Core Processing**: Canary core resolves dependencies, schedules jobs, executes them, persists results, and reports status

The extension does not modify Canary's core execution model; it provides a Python interface to describe jobs that Canary will execute.

Canonical Directive Namespace
-----------------------------

The authoritative directive namespace is:

.. code-block:: python

   import canary_pyt
   canary_pyt.directives.directive_name(*args, **kwargs)

The deprecated ``canary.directives`` namespace exists for backward compatibility only and should not be used in new code.

Implementation Model
--------------------

``canary_pyt`` follows a two-phase execution model:

1. **Discovery/Loading Phase**:
   - ``PYTLoader`` executes the ``.pyt`` file with ``__name__ == "__load__"``
   - Directives are monkeypatched to a ``DirectiveRecorder``
   - File execution records directive calls without running test logic
   - Both ``canary_pyt.directives`` and ``canary.directives`` are monkeypatched for compatibility

2. **Generation Phase**:
   - ``DirectiveRecorder`` stores directive name, arguments, keyword arguments, file, and line number
   - ``PYTAdapter`` applies recorded directives to a ``PYTModel``
   - ``PYTModel`` stores directive effects in reducible fields
   - ``PYTLockEmitter`` converts the model into ``JobSpecIR`` objects

Supported Backends
------------------

``canary_pyt`` supports multiple scheduler backends:

- **Local**: Default Canary execution
- **HPC**: Through ``canary_hpc`` extension (Slurm, PBS, Flux, Shell)
- **Distributed**: Through ``canary_dist`` extension
- **Other**: Any backend supported by Canary's resource pool system

When to Use canary_pyt
----------------------

Use ``canary_pyt`` when you need:

- Complex test parameterization
- Explicit dependency graphs between tests
- Resource-aware test scheduling (CPU, GPU, nodes)
- Conditional test activation based on options, keywords, or parameters
- Composite analysis workflows
- Reproducible test environments with assets and baselines

Use simpler formats (like basic Python scripts) when you need:

- Quick ad-hoc testing
- Simple smoke tests
- Tests without parameterization or dependencies

Example: Minimal .pyt Job
--------------------------

.. code-block:: python

   # Import the canonical directive namespace
   import canary_pyt

   # Define test metadata and requirements
   canary_pyt.directives.keywords("smoke", "unit")
   canary_pyt.directives.timeout(30)

   # Test logic
   def test_function():
       # Access test instance at runtime
       instance = canary.get_instance()
       print(f"Running {instance.name}")
       assert True

   if __name__ == "__main__":
       test_function()

This example shows:

- Import of ``canary_pyt`` (not deprecated ``canary``)
- Directive usage at module level
- Test logic guarded by ``if __name__ == "__main__"``
- No side effects during discovery phase

See Also
--------

- :doc:`file-structure`: Recommended ``.pyt`` file organization
- :doc:`directives`: Overview of available directives
- :doc:`directive-reference/index`: Complete directive reference
- :doc:`parameterization`: Test parameterization patterns
- :doc:`patterns`: Common ``.pyt`` usage patterns
