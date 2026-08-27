.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-example-simple:

Simple Test Example
===================

This example demonstrates a minimal but complete Canary test that you can use as
a template for your own tests.

Complete Example Code
---------------------

.. code-block:: python
   :caption: simple_test.pyt

   import canary
   import canary_pyt

   canary_pyt.directives.keywords("tutorial", "simple")
   canary_pyt.directives.description("A simple Canary test")

   def main():
       instance = canary.get_instance()
       
       # Simple test logic
       result = 2 + 2
       expected = 4
       
       if result != expected:
           raise ValueError(f"Expected {expected}, got {result}")
       
       print(f"✅ Test passed: {result} == {expected}")
       instance.add_measurement("calculation", result)

   if __name__ == "__main__":
       main()

How to Use This Example
-----------------------

1. **Copy the code** into a file named ``simple_test.pyt``

2. **Run the test**:

   .. code-block:: console

      python3 -m canary run simple_test.pyt

3. **Check results**:

   .. code-block:: console

      python3 -m canary status -rA

4. **View output**:

   .. code-block:: console

      cat TestResults/simple_test/canary-out.txt

Key Features Demonstrated
-------------------------

1. **Basic Structure**: Shows the fundamental test anatomy
2. **Directives**: Uses ``keywords()`` for test categorization
3. **Instance Access**: Demonstrates accessing test metadata
4. **Simple Validation**: Includes basic result checking
5. **Clean Output**: Shows proper test reporting

Customizing This Example
------------------------

To adapt this example for your needs:

1. **Change the test name**: Rename the file and update content
2. **Add keywords**: Modify the ``keywords()`` directive
3. **Update logic**: Replace the calculation with your test code
4. **Add validation**: Include appropriate result checking
5. **Add directives**: Include resource requirements, timeouts, etc.

Example Variations
------------------

**Data Processing Version**

.. code-block:: python
   :caption: simple_data.pyt

   import canary
   import canary_pyt

   canary_pyt.directives.keywords("data", "processing")
   canary_pyt.directives.copy("input.txt")

   def main():
       instance = canary.get_instance()
       
       # Read input
       with open("input.txt", "r") as f:
           data = f.read()
       
       # Process data
       result = process_data(data)
       
       # Save output
       with open("output.txt", "w") as f:
           f.write(result)
       
       # Mark as artifact
       canary_pyt.directives.artifact("output.txt")
       
       print(f"Processed {len(data)} bytes -> {len(result)} bytes")

**Parameterized Version**

.. code-block:: python
   :caption: simple_param.pyt

   import canary
   import canary_pyt

   canary_pyt.directives.keywords("param", "math")
   canary_pyt.directives.parameterize("value", [1, 2, 3, 5, 8])

   def main():
       instance = canary.get_instance()
       value = instance.parameters.value
       
       result = value * 2
       print(f"Doubled {value} -> {result}")
       
       # Add measurement
       instance.add_measurement("input", value)
       instance.add_measurement("output", result)

**External Command Version**

.. code-block:: python
   :caption: simple_command.pyt

   import subprocess
   import canary_pyt

   canary_pyt.directives.keywords("external", "command")
   canary_pyt.directives.timeout(10)

   def main():
       # Run external command
       result = subprocess.run(
           ["echo", "Hello from Canary"],
           capture_output=True,
           text=True
       )
       
       # Check result
       if result.returncode != 0:
           raise RuntimeError("Command failed")
       
       print(f"Command output: {result.stdout.strip()}")

.. tip::

    For more complete examples, see:

    - :doc:`/tutorial/examples/parameterized`: Parameterized test patterns
    - :doc:`/tutorial/examples/with-assets`: Asset and artifact management
    - :doc:`/tutorial/examples/composite`: Composite analysis workflows

.. seealso::

   - :doc:`/tutorial/quickstart`: Quickstart guide
   - :doc:`/tutorial/basics/first-test`: First test tutorial
   - :doc:`/tutorial/examples/parameterized`: Parameterized example
   - :doc:`/extensions/pyt/directives`: All available directives