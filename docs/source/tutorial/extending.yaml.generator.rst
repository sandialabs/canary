.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-extending-yaml-generator:

The generator class
===================

The generator is responsible for two things:

* identifying which files it can interpret; and
* turning those files into runnable test specs.

In the YAML plugin, this is implemented by :class:`~YAMLTestGenerator`.

File matching via ``file_patterns``
-----------------------------------

The generator advertises which filenames it recognizes using :attr:`~YAMLTestGenerator.file_patterns`:

.. literalinclude:: /static/yaml_generator.py
   :language: python
   :pyobject: YAMLTestGenerator
   :lines: 1-25

Only files matching these patterns are considered YAML test files by this generator.

Generating cases with ``lock()``
--------------------------------

The core method is :meth:`~YAMLTestGenerator.lock`. It reads the YAML, validates it, expands any
parameter combinations, and returns a list of :class:`~canary.ResolvedSpec` objects (one per runnable
test case):

.. literalinclude:: /static/yaml_generator.py
   :language: python
   :pyobject: YAMLTestGenerator.lock

Implementing ``describe()``
---------------------------

A generator can optionally implement :meth:`~YAMLTestGenerator.describe` to provide human-readable
output for ``canary describe FILE``. This is extremely useful when developing a new generator
because it exercises parsing and case generation without running anything.

.. literalinclude:: /static/yaml_generator.py
   :language: python
   :pyobject: YAMLTestGenerator.describe
