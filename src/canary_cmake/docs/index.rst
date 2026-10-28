.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

CMake Support
=============

The ``canary_cmake`` extension provides CMake and CTest integration for Canary.

**Extension type**: CMake/CTest integration, job-definition generator, CMake module.

Use ``canary_cmake`` when you want Canary to run tests discovered from a CMake
build tree or when you want CMake functions that generate Canary-aware test
definitions.

Prerequisites
-------------

- A CMake build tree for CTest discovery, or a CMake project that includes the
  Canary module.
- ``ctest`` available in ``PATH`` for CTest-based workflows.

Quick Start
-----------

Run tests directly from a CMake build directory:

.. code-block:: console

   canary run path/to/cmake-build

.. note::

   ``canary_cmake`` is a **built-in** canary extension, included in the
   ``canary-wm`` package.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   overview
   ctest-discovery
   ctest-properties
   status-and-regex
   fixtures-and-dependencies
   resources
   environment
   cmake-module
   ctest-example
   limitations

See Also
--------

- :doc:`/user/commands/run`: Canary run command reference
- :doc:`/user/usage.cmake`: User guide for CMake, CTest, and CDash workflows
- :doc:`/user/basics.job`: Canary job execution model
