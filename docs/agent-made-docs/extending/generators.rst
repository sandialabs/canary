.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-generators:

Generators
==========

Job generators transform user-facing job definitions into standardized JobSpecIR or JobSpec objects. Generators enable Canary to support diverse input formats while maintaining a consistent execution model.

AbstractTestGenerator
---------------------

The base class for all generators is ``AbstractTestGenerator``:

.. code-block:: python

   from canary import AbstractTestGenerator

   class MyGenerator(AbstractTestGenerator):
       file_patterns = ("*.myformat",)

       def describe(self, on_options=None):
           return "My custom test format"

       def lock(self, on_options=None):
           return [create_job_spec()]

Key Generator Methods
---------------------

**file_patterns**: Define file patterns for discovery

.. code-block:: python

   class MyGenerator(AbstractTestGenerator):
       file_patterns = ("*.myext", "*.myother")

**matches()**: Check if generator can handle a file

.. code-block:: python

   def matches(self, root, path):
       return path.endswith(".myformat")

**describe()**: Provide human-readable description

.. code-block:: python

   def describe(self, on_options=None):
       return f"Custom format generator for {self.file}"

**lock()**: Generate JobSpecIR objects

.. code-block:: python

   def lock(self, on_options=None):
       specs = []
       # Parse file and create job specifications
       for test_definition in parse_file(self.file):
           spec = create_job_spec(test_definition)
           specs.append(spec)
       return specs

Generator Registration
----------------------

Register generators using the ``canary_testcase_generator`` hook:

.. code-block:: python

   @canary.hookimpl
   def canary_testcase_generator(root, path):
       if path.endswith(".myformat"):
           return MyGenerator(root, path)

JobSpecIR Creation
------------------

Create JobSpecIR objects with required fields:

.. code-block:: python

   from canary import JobSpecIR

   def create_job_spec(test_def):
       return JobSpecIR(
           name=test_def["name"],
           file_path=str(self.file),
           file_root=self.root,
           family=test_def.get("family", "custom"),
           parameters=test_def.get("parameters", {}),
           directives=test_def.get("directives", []),
           required_resources=test_def.get("resources", []),
           dependencies=[]
       )

Dependency Selectors
--------------------

Define dependencies using dependency selectors:

.. code-block:: python

   from canary import DependencySelector

   def create_dependencies(test_def):
       deps = []
       if "depends_on" in test_def:
           for pattern in test_def["depends_on"]:
               selector = DependencySelector(
                   pattern=pattern,
                   when=test_def.get("when", "always")
               )
               deps.append(selector)
       return deps

Generator Best Practices
------------------------

**File Discovery**:

- Use clear file patterns for discovery
- Implement efficient file matching
- Handle edge cases (symlinks, missing files)

**Error Handling**:

- Validate input files thoroughly
- Provide meaningful error messages
- Use Canary's logging system

**Performance**:

- Parse files efficiently
- Cache parsed data where appropriate
- Minimize I/O operations

**Documentation**:

- Document supported file format
- Provide examples of job definitions
- Explain generator-specific features

Generator Examples
------------------

**Simple YAML Generator**:

.. code-block:: python

   import yaml
   import canary

   class YamlGenerator(canary.AbstractTestGenerator):
       file_patterns = ("*.yaml", "*.yml")

       def describe(self, on_options=None):
           return f"YAML test generator: {self.file}"

       def lock(self, on_options=None):
           with open(self.file, 'r') as f:
               data = yaml.safe_load(f)

           specs = []
           for test_name, test_config in data.get("tests", {}).items():
               spec = canary.JobSpecIR(
                   name=test_name,
                   file_path=str(self.file),
                   file_root=self.root,
                   family="yaml",
                   parameters=test_config.get("parameters", {}),
                   directives=test_config.get("directives", [])
               )
               specs.append(spec)
           return specs

**Parameterized Test Generator**:

.. code-block:: python

   import canary
   from itertools import product

   class ParamGenerator(canary.AbstractTestGenerator):
       file_patterns = ("*.param",)

       def lock(self, on_options=None):
           specs = []
           base_spec = create_base_spec(self.file)

           # Generate parameterized variants
           params = base_spec.parameters
           param_names = list(params.keys())
           param_values = list(params.values())

           for combo in product(*param_values):
               param_dict = dict(zip(param_names, combo))

               spec = canary.JobSpecIR(
                   name=f"{base_spec.name}.{format_params(param_dict)}",
                   file_path=str(self.file),
                   file_root=self.root,
                   family=base_spec.family,
                   parameters=param_dict,
                   directives=base_spec.directives
               )
               specs.append(spec)

           return specs

Generator Testing
-----------------

Test generators with sample files:

.. code-block:: python

   def test_generator():
       # Create test file
       test_file = Path("/tmp/test.myformat")
       test_file.write_text("test: example")

       # Create generator
       generator = MyGenerator("/tmp", "test.myformat")

       # Test methods
       assert generator.matches("/tmp", "test.myformat")
       assert "example" in generator.describe()

       # Test job generation
       specs = generator.lock()
       assert len(specs) == 1
       assert specs[0].name == "example"

Generator Troubleshooting
-------------------------

**Generator Not Found**:

- Verify file patterns match
- Check ``canary_testcase_generator`` hook registration
- Ensure file exists and is readable

**Job Generation Failures**:

- Validate input file format
- Check for parsing errors
- Verify required fields are present

**Performance Issues**:

- Profile file parsing
- Optimize specification creation
- Consider incremental parsing

See Also
--------

- :doc:`plugins`: Plugin registration
- :doc:`hooks`: Generator-related hooks
- :doc:`../user/generators`: Core generator concepts
- :doc:`../user/jobs`: Job specification structure