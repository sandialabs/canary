.. _extending-generator:

User defined test generator
===========================

``nvtest`` generates test cases from ``.pyt``, ``.vvt``, and ``CTestTestFile.cmake`` files.
Each generator is implemented as a subclass of :class:`~_nvtest.generator.AbstractTestGenerator`.  Custom test
generators can also be created by subclassing :class:`~_nvtest.generator.AbstractTestGenerator` and defining the
:meth:`~_nvtest.generator.AbstractTestGenerator.matches`,
:meth:`~_nvtest.generator.AbstractTestGenerator.describe`, and
:meth:`~_nvtest.generator.AbstractTestGenerator.lock` methods.

Consider the following YAML test input:

.. code-block:: yaml

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
    https://cee-gitlab.sandia.gov/ascic-test-infra/plugins/nvtest-yaml


Example implementation
----------------------

.. literalinclude:: /static/yaml_generator.py
    :language: python
    :lines: 1-88


The ``YAMLTestFile.lock()`` returns a list of ``YAMLTestCase`` test cases, defined below:

.. literalinclude:: /static/yaml_generator.py
    :language: python
    :lines: 89-
