.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_vvtest:

VVTest Job-Definition Generator
===============================

The ``canary_vvtest`` extension provides support for VVTest-style ``.vvt`` files, enabling Canary to discover and execute VVTest test suites.

**Extension type**: VVTest compatibility generator.

Use ``canary_vvtest`` when you need to run existing ``.vvt`` suites under
Canary without rewriting them to ``.pyt`` first.

If you want to run an existing vvtest suite under Canary, start with
:doc:`/user/usage.vvtest`. The pages here focus on file format details,
parser behavior, compatibility notes, and migration guidance.

Prerequisites
-------------

- Existing ``.vvt`` test files.
- Willingness to accept documented compatibility differences from native
  ``vvtest`` behavior.

Quick Start
-----------

Point Canary at a directory containing ``.vvt`` files:

.. code-block:: console

   canary run path/to/vvtest-suite

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

- :doc:`/extensions/exts/canary_pyt/index`: Python job-definition reference
- :doc:`/extensions/exts/canary_cmake/index`: CMake and CTest integration
- :doc:`/user/usage.vvtest`: User guide for running VVTest-format test scripts
- :doc:`/user/basics.job`: Canary job execution model
