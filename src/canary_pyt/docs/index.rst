.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_pyt:

Python Job-Definition Generator
===============================

The ``canary_pyt`` extension is the **reference Python job-definition generator** for Canary. It provides a Python-based domain-specific language for defining test jobs using directives, enabling complex test scenarios with parameterization, dependencies, resource requirements, and conditional activation.

**Extension type**: reference Python job-definition generator, directive interpreter.

.. note::

   ``canary_pyt`` is a **built-in** canary extension, included in the
   ``canary-wm`` package.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   overview
   file-structure
   execution-model
   directives
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

.. note::

   See :doc:`/user/directives/index` for the auto-generated directive reference.

See Also
--------

- :doc:`/user/usage.cmake`: CMake and CTest integration
- :doc:`/extensions/exts/canary_hpc/index`: HPC scheduler integration
- :doc:`/user/basics.job`: Canary job execution model
- :doc:`/user/basics.resource`: Canary resource pools and allocation
- :doc:`/user/reporting`: Canary reporting overview
