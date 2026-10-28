.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

canary user's guide
===================

Start here when you have a task in mind, such as running CTest tests, using an
HPC scheduler, or working with existing ``.vvt`` suites. For extension internals
and implementation details, use :doc:`/extensions/index`.

.. toctree::
   :caption: Getting started
   :maxdepth: 1

   about
   installing
   getting-help
   getting-started

.. toctree::
   :caption: Basics and usage
   :maxdepth: 2

   basics
   usage

.. rubric:: Common Workflows

- :doc:`usage.cmake` for CMake, CTest, and CDash workflows
- :doc:`usage.hpc` for scheduler-backed HPC execution
- :doc:`usage.vvtest` for running existing ``.vvt`` suites
- :doc:`usage.gitlab` for GitLab reporting

.. toctree::
   :caption: Configuration
   :maxdepth: 2

   configuration

.. toctree::
   :caption: Creating reports
   :maxdepth: 2

   reporting

.. toctree::
   :caption: Extending canary through plugins
   :maxdepth: 2

   extending

.. toctree::
   :caption: Commands and directives
   :maxdepth: 1

   commands/index
   directives/index
   util
