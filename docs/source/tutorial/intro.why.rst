.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Why canary?
===========

``canary`` offers several advantages over similar testing tools:

**Speed**: Hierarchical parallelism is used to run tests asynchronously, optimizing resource utilization and speeding up the testing process.  See :ref:`basics-resource` for more.

**Python**: ``canary`` is an easy to install `Python <python.org>`_ library.

**Integration**: ``canary`` :ref:`integrates<integrations>` with popular developer tools like :ref:`CMake <integrations-cmake>`, :ref:`CDash <integrations-cdash>`, and :ref:`GitLab <integrations-gitlab>`, streamlining the testing and continuous integration (CI) processes.

**Extensibility**: ``canary`` can be extended through :ref:`user plugins <extending>`, allowing developers to customize their test sessions according to their specific needs.
