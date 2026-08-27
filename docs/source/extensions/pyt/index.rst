.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

canary_pyt Extension
====================

The ``canary_pyt`` extension is the **reference Python job-definition generator** for Canary. It provides a Python-based domain-specific language for defining test jobs using directives, enabling complex test scenarios with parameterization, dependencies, resource requirements, and conditional activation.

**Extension type**: reference Python job-definition generator, directive interpreter, compatibility layer for legacy ``canary.directives`` imports.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   overview
   file-structure
   execution-model
   directives
   directive-reference/index
   parameterization
   dependencies
   resources
   assets
   artifacts
   baselines
   expected-results
   composite-analysis
   test-instance
   conditional-activation
   explicit-ids
   patterns
   limitations

See Also
--------

- :doc:`/extensions/cmake/index`: CMake/CTest integration
- :doc:`/extensions/hpc/index`: HPC scheduler integration
- Canary core documentation (job execution, resource pools, reporting)
