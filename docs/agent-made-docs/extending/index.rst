.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-index:

Extension Authoring Guide
=========================

Canary's plugin architecture enables powerful extensions through a comprehensive hook system. This guide covers all aspects of extension development, from basic plugins to advanced integration points.

Canary's Plugin Architecture
-----------------------------

Canary uses `pluggy <https://pluggy.readthedocs.io/>`_ for its plugin system, providing a flexible hook-based architecture that allows extensions to:

- **Register commands**: Add new subcommands to the Canary CLI
- **Create job generators**: Support new test file formats and job definitions
- **Extend configuration**: Add custom configuration options and validation
- **Modify runtime behavior**: Hook into collection, selection, and execution lifecycle
- **Enhance resource management**: Add custom resource types and allocation strategies
- **Create reporters**: Generate custom reports and output formats
- **Add measurements**: Collect and analyze execution metrics

Plugin Discovery and Loading
----------------------------

Canary discovers and loads plugins through multiple mechanisms:

1. **Built-in plugins**: Core Canary functionality
2. **Setuptools entry points**: ``canary`` entry point group
3. **Environment variable**: ``CANARY_PLUGINS=plugin1,plugin2``
4. **Configuration**: ``plugins`` field in configuration files
5. **Command line**: ``-p NAME`` option for local plugins

Extensions integrate seamlessly with Canary's lifecycle, providing custom behavior while maintaining compatibility with the core framework.

Extension Points Overview
-------------------------

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   plugins
   hooks
   generators
   commands
   configuration
   resources
   reporters
   measurements
   docs

Getting Started
---------------

To begin extending Canary:

1. **Create a plugin module**:

   .. code-block:: python

      # my_plugin.py
      import canary

      @canary.hookimpl
      def canary_addoption(parser):
          parser.add_argument("--my-option", help="My custom option")

2. **Load your plugin**:

   .. code-block:: console

      $ canary -p my_plugin run .

3. **Develop incrementally**: Start with simple hooks, then expand functionality

Best Practices
--------------

- **Follow Canary's lifecycle**: Hook into appropriate phases without disrupting flow
- **Maintain compatibility**: Avoid breaking core assumptions and APIs
- **Document extensions**: Provide clear documentation for users
- **Test thoroughly**: Validate extension behavior in different scenarios
- **Use source-compatible hooks**: Ensure hooks work across Canary versions

Extension Development Workflow
------------------------------

1. **Identify extension points**: Determine which hooks provide needed functionality
2. **Implement hooks**: Create plugin functions with ``@canary.hookimpl`` decorator
3. **Test locally**: Use ``-p`` flag for rapid iteration
4. **Package as entry point**: Register for automatic discovery
5. **Document behavior**: Explain extension capabilities and usage

See Also
--------

- :doc:`plugins`: Plugin loading and management
- :doc:`hooks`: Comprehensive hook reference
- :doc:`generators`: Job generator development
- :doc:`../user/concepts`: Core Canary concepts
- :doc:`../user/workspaces`: Workspace architecture
