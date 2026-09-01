.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

What is canary?
===============

``canary`` is a Python-based test framework for scientific applications. Given one or more paths,
it can:

* discover tests from multiple sources (for example ``.pyt`` / ``.vvt`` files, or CMake/CTest);
* expand discovered tests into one or more runnable **test cases** (for example, via parameterization);
* run test cases asynchronously; and
* report results.

Most behavior in ``canary`` is implemented via plugins (using ``pluggy``). This keeps the core
engine format-agnostic: adding a new test source, launcher, or reporting backend is typically done
by providing additional hook implementations.

Why canary?
-----------

``canary`` is designed for test workloads that need to run across diverse machines and resource
configurations (from laptops to HPC systems). It emphasizes:

* **Asynchronous execution** with resource-aware scheduling.
* **Workflow-style testing** via parameter sweeps and dependencies.
* **Extensibility** via a plugin architecture (test sources, launchers, schedulers, reports).

The remainder of this tutorial introduces these features using small, runnable examples.
