.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial:

Canary Tutorial
===============

Welcome to the Canary tutorial! This guide will walk you through Canary's core concepts
and practical usage patterns, from basic test execution to advanced workflow automation.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   quickstart

.. toctree::
   :maxdepth: 2
   :caption: Core Concepts

   basics/first-test
   basics/test-structure
   basics/running-tests
   basics/status-codes

.. toctree::
   :maxdepth: 2
   :caption: Practical Patterns

   intermediate/test-hooks
   intermediate/parameterization
   intermediate/dependencies
   intermediate/assets
   intermediate/resources

.. toctree::
   :maxdepth: 2
   :caption: Advanced Topics

   advanced/hooks
   advanced/composite
   advanced/hpc
   advanced/ci-integration
   advanced/custom-generators

.. toctree::
   :maxdepth: 1
   :caption: Complete Examples

   examples/simple
   examples/parameterized
   examples/with-assets
   examples/composite

Tutorial Approach
-----------------

This tutorial is designed for **progressive learning**:

1. **Quickstart**: Get running in 5 minutes
2. **Core Concepts**: Understand the fundamentals
3. **Practical Patterns**: Solve common problems
4. **Advanced Topics**: Complex workflows and integration
5. **Complete Examples**: Ready-to-use templates

Each section builds on the previous one, but you can also jump to specific topics as needed.

.. note::

   All examples use Python job definitions (``.pyt`` files) which provide access to the full
   Canary ecosystem. For VVTest compatibility, see :doc:`/extensions/vvtest/index`.

.. tip::

   Want to try the examples? Fetch them with:

   .. code-block:: console

      python3 -m canary fetch examples

   Then navigate to the ``tutorial/examples`` directory.