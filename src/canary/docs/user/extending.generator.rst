.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-generator:

User defined test generator
===========================

What job generators do
-----------------------

Job generators are plugins that bridge user-facing job definitions with ``canary``'s
internal job representation.  They are responsible for:

1. **Discovery** — scanning files and directories to find job definitions
2. **Parsing** — interpreting job specifications in their native format
3. **Validation** — checking job definitions for correctness and completeness
4. **Conversion** — emitting ``JobSpecIR`` or ``JobSpec`` objects for ``canary`` core
5. **Metadata** — providing additional information about the jobs

Why there is no universal input format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``canary`` intentionally does not define a single universal job-definition file
format because different domains have different requirements, existing tools use
established formats, and new formats can be added without changing core
functionality.  This design allows ``canary`` to integrate with existing workflows
while providing a consistent execution model.

Built-in generator extensions
------------------------------

``canary`` ships three bundled generators:

``canary_pyt``
  Python-based job definitions (``.pyt`` files).  The primary format for new test
  suites and the reference implementation for extension authors.  Uses Python
  function calls (``canary.directives.*``) to define test behaviour.

``canary_cmake``
  CMake/CTest integration.  Consumes ``CTestTestFile.cmake`` and CMakeLists-driven
  test definitions.  See :ref:`canary-cmake`.

``canary_vvtest``
  VVTest compatibility layer (``.vvt`` files).  Provides backward compatibility
  with existing VVTest workflows.  See :ref:`canary-vvtest`.

Writing a new generator
-----------------------

``canary`` generates jobs from ``.pyt``, ``.vvt``, and ``CTestTestFile.cmake`` files.  Each generator is implemented as a subclass of :class:`~_canary.generator.AbstractTestGenerator`.  User defined test generators can also be created by subclassing :class:`~_canary.generator.AbstractTestGenerator` and defining the :meth:`~_canary.generator.AbstractTestGenerator.matches`, :meth:`~_canary.generator.AbstractTestGenerator.describe`, and :meth:`~_canary.generator.AbstractTestGenerator.lock` methods.  User defined test generators are registered with the :func:`~_canary.plugins.hookspec.canary_testcase_generator` plugin hook.

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

The cartesian product of parameters should be taken and each combination used to generate a job.  Each job should execute the ``script``, first expanding variables of the form ``$variable`` or ``${variable}`` with the parameter values.

In the sections that follow, a test generator will be developed that parses this and other similar
test files.

.. note::

    The completed test file generator can be seen at
    https://github.com/sandialabs/canary-yaml


Example implementation
----------------------

.. literalinclude:: /static/yaml_generator.py
    :language: python

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

The cartesian product of parameters should be taken and each combination used to generate a job.  Each job should execute the ``script``, first expanding variables of the form ``$variable`` or ``${variable}`` with the parameter values.

In the sections that follow, a test generator will be developed that parses this and other similar
test files.

.. note::

    The completed test file generator can be seen at
    https://github.com/sandialabs/canary-yaml


Example implementation
----------------------

.. literalinclude:: /static/yaml_generator.py
    :language: python
