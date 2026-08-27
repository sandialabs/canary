.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-test-structure:

Anatomy of a Canary Test
=========================

This guide explores the structure of Canary tests in detail, covering all the
components that make up a complete test definition.

Basic Structure
---------------

A Canary test file (``.pyt``) has this fundamental structure:

.. code-block:: python

   # 1. Imports
   import canary
   import canary_pyt
   
   # 2. Directives (Metadata)
   canary_pyt.directives.keywords("category", "type")
   canary_pyt.directives.description("What this test does")
   
   # 3. Test Function
   def main():
       # Test logic
       instance = canary.get_instance()
       # ... test operations ...
   
   # 4. Entry Point
   if __name__ == "__main__":
       main()

The Four Layers of Test Structure
----------------------------------

Layer 1: File Metadata
^^^^^^^^^^^^^^^^^^^^^^^

The test file itself has properties:

- **Filename**: Should be descriptive (e.g., ``test_addition.pyt``)
- **Location**: Path determines test organization
- **Extensions**: ``.pyt`` for Python tests, ``.vvt`` for legacy tests

Layer 2: Directives
^^^^^^^^^^^^^^^^^^^

Directives configure test behavior:

.. code-block:: python

   # Core directives
   canary_pyt.directives.keywords("math", "unit")
   canary_pyt.directives.description("Test basic arithmetic")
   canary_pyt.directives.timeout(30)  # 30 second timeout
   
   # Resource directives
   canary_pyt.directives.cpus(2)      # Require 2 CPUs
   canary_pyt.directives.gpus(1)      # Require 1 GPU
   canary_pyt.directives.memory("4GB")  # Memory requirement
   
   # Asset directives
   canary_pyt.directives.copy("input.dat")      # Copy input file
   canary_pyt.directives.link("data.txt")       # Link input file
   canary_pyt.directives.artifact("output.json") # Save output artifact

Layer 3: Test Logic
^^^^^^^^^^^^^^^^^^^

The ``main()`` function contains your test logic:

.. code-block:: python

   def main():
       instance = canary.get_instance()
       
       # Setup
       setup_test_environment()
       
       # Execute
       result = run_test_operations()
       
       # Validate
       validate_results(result)
       
       # Cleanup
       cleanup_resources()

Layer 4: Runtime Context
^^^^^^^^^^^^^^^^^^^^^^^^^

Canary provides runtime information:

.. code-block:: python

   def main():
       instance = canary.get_instance()
       
       # Access instance properties
       print(f"Test name: {instance.name}")
       print(f"Test ID: {instance.id}")
       print(f"Parameters: {instance.parameters}")
       print(f"Working dir: {instance.workspace}")
       
       # Access environment
       workspace = instance.workspace
       session = instance.session
       
       # Add measurements
       instance.add_measurement("accuracy", 0.95)
       instance.add_measurement("duration", 2.5)

Common Test Patterns
--------------------

Simple Validation Test
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   def main():
       result = compute_something()
       expected = get_expected_value()
       
       if result != expected:
           raise ValueError(f"Expected {expected}, got {result}")
       
       print("✅ Test passed")

Data Processing Test
^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   def main():
       # Copy input data
       canary_pyt.directives.copy("input.csv")
       
       # Process data
       df = pandas.read_csv("input.csv")
       result = process_data(df)
       
       # Save output
       result.to_json("output.json")
       canary_pyt.directives.artifact("output.json")

Parameterized Test
^^^^^^^^^^^^^^^^^^

.. code-block:: python

   # At file level
   canary_pyt.directives.parameterize("size", [10, 100, 1000])
   
   def main():
       instance = canary.get_instance()
       size = instance.parameters.size
       
       # Run test with specific size
       run_test_with_size(size)

Test Organization Strategies
----------------------------

By Functionality
^^^^^^^^^^^^^^^^

.. code-block:: text

   tests/
   ├── math/
   │   ├── addition.pyt
   │   ├── subtraction.pyt
   │   └── multiplication.pyt
   ├── io/
   │   ├── file_read.pyt
   │   └── file_write.pyt
   └── network/
       └── http_request.pyt

By Complexity
^^^^^^^^^^^^^

.. code-block:: text

   tests/
   ├── unit/
   │   └── individual_components.pyt
   ├── integration/
   │   └── component_interaction.pyt
   └── system/
       └── end_to_end.pyt

By Data
^^^^^^^

.. code-block:: text

   tests/
   ├── small_data/
   │   └── quick_tests.pyt
   ├── medium_data/
   │   └── standard_tests.pyt
   └── large_data/
       └── performance_tests.pyt

Best Practices
--------------

1. **Single Responsibility**: Each test should verify one thing
2. **Descriptive Names**: Use clear, specific names
3. **Consistent Structure**: Follow the same pattern across tests
4. **Proper Directives**: Always include relevant metadata
5. **Explicit Validation**: Check conditions and fail clearly
6. **Resource Management**: Clean up temporary resources
7. **Measurements**: Record quantitative results
8. **Documentation**: Add comments for complex logic

.. seealso::

   - :doc:`first-test`: Your first complete test
   - :doc:`/extensions/pyt/directives`: All available directives
   - :doc:`/user/jobs`: Job lifecycle and structure
   - :doc:`/extensions/pyt/parameterization`: Parameterized tests