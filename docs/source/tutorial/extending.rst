.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-extending:

Extending canary
================

Most operations in ``canary`` are implemented as `pluggy <https://github.com/pytest-dev/pluggy>`_ hooks. Extending ``canary`` typically means writing a plugin that implements one or more hooks.

This section focuses on extending test discovery by adding a new **testcase generator**: a plugin
that teaches ``canary`` how to interpret a new input file format and generate runnable test cases.

.. toctree::
   :maxdepth: 1

   extending.overview
   extending.generator-concept
   extending.yaml-generator
   extending.install-and-use
