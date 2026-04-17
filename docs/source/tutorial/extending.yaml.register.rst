.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-extending-yaml-register:

Registering the generator
=========================

A testcase generator becomes active when a plugin registers it during collection. The YAML plugin
does this by implementing the ``canary_collectstart`` hook:

.. literalinclude:: /static/yaml_generator.py
   :language: python
   :pyobject: canary_collectstart

At runtime, ``canary`` creates a collector and calls the ``canary_collectstart`` hook on all loaded
plugins. The hook receives the collector object and can register one or more generators. From that
point on, the collector will use the registered generators when scanning the filesystem.

Key idea
--------

``canary`` does not have a single built-in “test format”. A test source (``.pyt``, ``.vvt``, YAML,
CTest, etc.) is enabled when a plugin registers a generator.

Common failure mode
-------------------

If YAML files are not being discovered, the first thing to check is whether the plugin package is
installed and loaded. If the plugin is not loaded, its ``canary_collectstart`` hook is never
called, and the generator is never registered.
