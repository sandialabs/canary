.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-extending:

Extending canary
================

Most operations in ``canary`` are implemented as `pluggy <https://github.com/pytest-dev/pluggy>`_ hooks. Extending ``canary`` typically means writing a plugin that implements one or more hooks.

Examples of plugin-provided behavior include:

* test sources and test generation (e.g., ``.pyt``, ``.vvt``, CTest);
* launching and execution backends;
* reporting and result post-processing;
* batched execution via external systems (e.g., ``canary_hpc``).

In this tutorial section we focus on adding support for a new *test input format* by implementing
a testcase generator hook.


.. toctree::
   :maxdepth: 1

   extending.generator-concept
   extending.yaml
