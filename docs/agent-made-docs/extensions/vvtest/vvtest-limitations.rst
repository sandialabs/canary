.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

VVTest Limitations
==================

Understanding the limitations of ``canary_vvtest`` helps avoid common pitfalls and ensures proper test authoring.

File Matching
-------------

### Only .vvt Files

Only files matching ``*.vvt`` are processed by ``canary_vvtest``:

.. code-block:: text

   # Only .vvt files are matched

### Unsupported Directives

Unsupported directives raise parse errors:

.. code-block:: text

   #VVT: unsupported_directive : arg  # Error

Include Files
-------------

### Must Exist

Include files must exist:

.. code-block:: text

   #VVT: include : missing.vvt  # Error

### Relative Paths

Include paths resolved relative to current file:

.. code-block:: text

   #VVT: include : common.vvt  # Relative to current file

Parameterization
----------------

### Generated Parameters

Generated parameter scripts must have expected JSON format:

.. code-block:: json

   [{"size": 10}, {"size": 20}]

### Dependency Count

Dependency count must match parameterization count:

.. code-block:: text

   #VVT: parameterize : size = 10 20 30
   #VVT: analyze : script.py  # Must match 3 parameters

DEPDIRMAP
---------

Currently empty in source (may be populated in future).

Compatibility
-------------

### Not All VVTest Features

Some VVTest features may not be supported:

- VVTest-specific runtime environment
- Custom VVTest plugins
- Advanced VVTest features

### Practical, Not Exact

Compatibility is practical but not exact:

- Behavior matches where possible
- Differences are documented
- Migration is recommended for full features

Best Practices
--------------

1. **Test Incrementally**:
   - Start with small test suites
   - Verify behavior before full adoption
   - Address issues early

2. **Validate Results**:
   - Compare VVTest vs Canary outputs
   - Check dependency graphs
   - Verify resource allocation

3. **Document Differences**:
   - Track compatibility notes
   - Note workarounds
   - Update documentation

4. **Plan Migration**:
   - Identify critical tests
   - Convert incrementally
   - Use both systems in parallel

See Also
--------

- :doc:`vvtest-compatibility`: Compatibility details
- :doc:`file-format`: File format reference
