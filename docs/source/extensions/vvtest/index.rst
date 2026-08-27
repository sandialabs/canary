.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

canary_vvtest Extension
========================

The ``canary_vvtest`` extension provides compatibility for VVTest-style ``.vvt`` files, enabling Canary to discover and execute legacy VVTest test suites. This extension bridges the gap between VVTest's historical influence on Canary and modern Canary workflows.

**Extension type**: VVTest compatibility generator and migration bridge.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   overview
   legacy-and-migration
   file-format
   vvtest-directives
   vvtest-parameterization
   vvtest-dependencies
   vvtest-analysis
   vvtest-assets-and-baselines
   vvtest-environment
   vvtest-compatibility
   vvtest-limitations

See Also
--------

- :doc:`/extensions/pyt/index`: Python job-definition reference
- :doc:`/extensions/cmake/index`: CMake/CTest integration
- Canary core documentation (job execution, resource pools, reporting)
