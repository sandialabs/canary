.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Introduction
============

What Canary Is
--------------

Canary is a plugin-based workflow and application-testing framework. It provides a flexible foundation for defining, scheduling, and executing jobs across diverse computing environments, from developer laptops to large-scale HPC systems.

Originally inspired by VVTest and developed for application testing, Canary has evolved into a general-purpose workflow execution framework. It automates software testing, manages analysis workflows, executes computational pipelines, and coordinates collections of dependent jobs.

Why Canary Exists
-----------------

Canary addresses the need for a unified framework that can:

- **Scale efficiently** across diverse hardware platforms using hierarchical parallelism
- **Unify workflow and testing** within a single framework, reducing tool proliferation
- **Provide Python-based definitions** with access to the full Python ecosystem
- **Integrate seamlessly** with common development tools like CMake, CDash, and GitLab
- **Extend flexibly** through a plugin architecture for customization

Historical Inspiration
----------------------

Canary draws inspiration from VVTest's strengths in scalable test execution while providing a more flexible foundation for broader workflow automation. Unlike VVTest, which focused primarily on testing, Canary is designed as a general workflow framework that can handle testing as a primary use case among many others.

Evolution into a General Framework
----------------------------------

While testing remains a primary use case, it is no longer the defining purpose of Canary. The framework has evolved to support:

- **Software testing** (unit tests, integration tests, regression tests)
- **Simulation workflows** (computational pipelines, analysis tasks)
- **Data processing** (validation checks, transformation stages)
- **General workflow automation** (any executable unit of work)

This evolution maintains backward compatibility with testing-focused use cases while providing the flexibility needed for broader workflow automation.

Core vs Extension Responsibilities
----------------------------------

Canary follows a clear separation between core functionality and extension capabilities:

**Canary Core** handles:

- Job discovery and collection
- Dependency resolution and graph construction
- Resource-aware scheduling and execution
- Result persistence and query
- Reporting and status tracking

**Extensions** provide:

- Job generators (input format support)
- Reporter plugins (output format support)
- Scheduler/execution backends
- Resource backends
- External integrations

This separation allows Canary to maintain a stable core while enabling flexible customization through plugins.

Common Use Cases
----------------

Canary is used for:

1. **Automated Software Testing**: Running test suites with complex dependencies and resource requirements
2. **Continuous Integration**: Integrating with CI/CD pipelines for automated testing and validation
3. **HPC Workflow Management**: Coordinating computational jobs across high-performance computing resources
4. **Analysis Pipelines**: Managing multi-stage data processing and analysis workflows
5. **Validation Workflows**: Executing validation checks and quality assurance processes
6. **General Workflow Automation**: Orchestrating any collection of executable tasks

Quick Start Example
-------------------

To get started quickly, fetch the bundled examples and run a basic test:

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary run ./basic, python3 -m canary status -rA]
   :cwd: /examples

This example demonstrates the core workflow: fetch examples, run tests, and check status.

Where to Go Next
----------------

To learn more about Canary's architecture and concepts:

- :doc:`concepts`: Understand the core architectural concepts and components
- :doc:`generators`: Learn about job generators and how they integrate with Canary
- :doc:`../extensions/pyt/index`: Explore the reference Python job-definition generator
- :doc:`../extensions/cmake/index`: Discover CMake/CTest integration
- :doc:`../extensions/vvtest/index`: Learn about VVTest compatibility

For hands-on usage, see the extension-specific documentation and command reference.