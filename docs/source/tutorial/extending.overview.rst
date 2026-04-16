.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-extending-overview:

Plugin-based architecture (high level)
======================================

``canary`` is built on ``pluggy``. Instead of hard-coding behavior, ``canary`` defines hooks (the
"what") and plugins provide hook implementations (the "how").

Examples of plugin-provided behavior include:

* test sources and test generation (e.g., ``.pyt``, ``.vvt``, CTest);
* launching and execution backends;
* reporting and result post-processing;
* batched execution via external systems (e.g., ``canary_hpc``).

In this tutorial section we focus on adding support for a new *test input format* by implementing
a testcase generator hook.
