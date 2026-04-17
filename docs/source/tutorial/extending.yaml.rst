.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-extending-yaml:

Worked example: a YAML testcase generator
=========================================

Consider the YAML test file:

.. code-block:: yaml

   tests:
     hello_yaml:
       keywords: [demo]
       script:
         - echo "hello from yaml"

This file can be turned into a runnable ``canary`` test spec in just a few lines of plugin code:

.. code-block:: python

   import canary

   @canary.hookimpl
   def canary_collectstart(collector) -> None:
       collector.add_generator(YAMLTestGenerator)

Further sections will describe how the generator recognizes files, validates YAML, and generates
one or more :class:`~canary.ResolvedSpec` objects.

.. toctree::
   :maxdepth: 1

   extending.yaml.register
   extending.yaml.generator
   extending.yaml.specs
