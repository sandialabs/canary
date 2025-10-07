.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-generator:

User defined test generator
===========================

``canary`` generates test cases from ``.pyt``, ``.vvt``, and ``CTestTestFile.cmake`` files.  Each generator is implemented as a subclass of :class:`~_canary.generator.AbstractTestGenerator`.  User defined test generators can also be created by subclassing :class:`~_canary.generator.AbstractTestGenerator` and defining the :meth:`~_canary.generator.AbstractTestGenerator.matches`, :meth:`~_canary.generator.AbstractTestGenerator.describe`, and :meth:`~_canary.generator.AbstractTestGenerator.lock` methods.  User defined test generators are registered with the :func:`~_canary.plugins.hookspec.canary_generator` plugin hook.

Consider the following YAML test input:

.. code-block:: yaml

    tests:
      hello_world:
        description: "A Hello world test"
        script:
        - echo "Hello, ${location}!"
        - echo "n = ${n}"
        keywords:
        - "hello"
        - "world"
        parameters:
          n: [2, 4, 8]
          location: ["World", "U.S.A", "Canada", "Mexico"]

The cartesian product of parameters should be taken and each combination used to generate a test case.  Each test case should execute the ``script``, first expanding variables of the form ``$variable`` or ``${variable}`` with the parameter values.

In the sections that follow, a test generator will be developed that parses this and other similar
test files.

.. note::

    The completed test file generator can be seen at
    https://github.com/sandialabs/canary-yaml


Example implementation
----------------------

.. literalinclude:: /static/yaml_generator.py
    :language: python
    :lines: 1-71


The ``YAMLTestGenerator.lock()`` returns a list of ``YAMLTestCase`` test cases, defined below:

.. literalinclude:: /static/yaml_generator.py
    :language: python
    :lines: 72-114


The user defined test generator is registered using the :meth:`~_canary.plugins.hookspec.canary_generator` plugin hook:

.. literalinclude:: /static/yaml_generator.py
    :language: python
    :lines: 115-
