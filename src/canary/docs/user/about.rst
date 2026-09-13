.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _introduction-about:

About canary
============

``canary`` is an application testing framework designed to test scientific applications. ``canary`` is inspired by `vvtest <https://github.com/sandialabs/vvtest>`_ and is designed to run tests on diverse hardware from laptops to super computing clusters.  ``canary`` not only validates the functionality of your application but can also serve as a workflow manager for analysts.  A "test" is an executable script with extension ``.pyt`` or ``.vvt`` [#]_.  If the exit code upon executing the script is ``0``, the test is considered to have passed, otherwise a non-passing :ref:`status <basics-status>` will be assigned.  ``canary``'s methodology is simple: given a path on the filesystem, ``canary`` recursively searches for test scripts, sets up the tests described in each script, executes them, and reports the results.

``canary`` offers several advantages over similar testing tools:

**Speed**: Hierarchical parallelism is used to run tests asynchronously, optimizing resource utilization and speeding up the testing process.  See :ref:`basics-resource` for more.

**Python**: Test files are written in `Python <python.org>`_, giving developers access to the full Python ecosystem.

**Integration**: ``canary`` integrates with popular developer tools like :ref:`CMake <canary-cmake>`, :ref:`CDash <integrations-cdash>`, and :ref:`GitLab <canary-gitlab>`, streamlining the testing and continuous integration (CI) processes.

**Extensibility**: ``canary`` can be extended through :ref:`user plugins <extending>`, allowing developers to customize their test sessions according to their specific needs.

Evolution into a general framework
------------------------------------

While testing remains a primary use case, ``canary`` is designed as a general workflow
execution framework.  It supports:

- **Software testing** — unit tests, integration tests, regression tests
- **Simulation workflows** — computational pipelines, analysis tasks
- **Data processing** — validation checks, transformation stages
- **General workflow automation** — any collection of executable tasks with dependencies

This design maintains full backward compatibility with testing-focused use cases while
providing flexibility for broader automation needs.

Core vs. extension responsibilities
--------------------------------------

``canary`` follows a clear separation between core functionality and extension
capabilities:

**Canary core** handles:

- Job discovery and collection
- Dependency resolution and execution graph construction
- Resource-aware scheduling and execution
- Result persistence and querying
- Reporting and status tracking

**Extensions** provide:

- Job generators (input format support: ``.pyt``, ``.vvt``, CMake/CTest, …)
- Reporter plugins (output format support: JUnit, CDash, HTML, …)
- Scheduler/execution backends (HPC, Flux, distributed pools, …)
- Resource backends and external integrations

This separation keeps the core stable while allowing the plugin ecosystem to evolve
independently.

Common use cases
----------------

1. **Automated software testing** — running test suites with complex dependencies and
   resource requirements
2. **Continuous integration** — integrating with CI/CD pipelines for automated testing
   and validation
3. **HPC workflow management** — coordinating computational jobs across
   high-performance computing resources
4. **Analysis pipelines** — managing multi-stage data processing and analysis
   workflows
5. **Validation workflows** — executing validation checks and quality assurance
   processes

.. [#] ``.pyt`` scripts are written in python while ``.vvt`` scripts can be any executable recognized by the system, though scripts written in Python can take advantage of the full ``canary`` ecosystem.
