.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_vvtest:

VVTest Job-Definition Generator
===============================

The ``canary_vvtest`` extension provides support for VVTest-style ``.vvt`` files, enabling Canary to discover and execute VVTest test suites.

**Extension type**: VVTest compatibility generator.

.. note::

   ``canary_vvtest`` is a **built-in** canary extension, included in the
   ``canary-wm`` package.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   overview
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

- ``canary_pyt`` extension: Python job-definition reference
- ``canary_cmake`` extension: CMake/CTest integration
- Canary core documentation (job execution, resource pools, reporting)
