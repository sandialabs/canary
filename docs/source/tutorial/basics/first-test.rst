.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-first-test:

Your First Canary Test
======================

This tutorial explores a minimal Canary test in detail, explaining each component
and how Canary processes it.

The Complete Test File
----------------------

Here's a minimal but complete Canary test:

.. code-block:: python
   :caption: minimal.pyt
   :name: minimal-test-example

   import canary
   import canary_pyt

   # Metadata directives
   canary_pyt.directives.keywords("tutorial", "basic")
   canary_pyt.directives.description("A minimal Canary test")

   def main():
       """Test execution function."""
       instance = canary.get_instance()
       
       # Access test information
       print(f"Test name: {instance.name}")
       print(f"Test ID: {instance.id}")
       
       # Perform the actual test work
       result = 2 + 2
       print(f"Calculation: 2 + 2 = {result}")
       
       # Validate the result
       if result != 4:
           raise ValueError(f"Expected 4, got {result}")
       
       print("✅ Test passed!")

   if __name__ == "__main__":
       main()

Anatomy of a Canary Test
------------------------

A Canary test has three main parts:

1. **Directives (Metadata)**
   ```python
   canary_pyt.directives.keywords("tutorial", "basic")
   canary_pyt.directives.description("A minimal Canary test")
   ``````````````````````````````````````````````````````````
   
   Directives provide metadata about the test:
   
   - **keywords**: Labels for filtering (e.g., ``-k tutorial``)
   - **description**: Human-readable description
   - **timeout**: Maximum runtime
   - **resources**: CPU/GPU requirements
   
   See :doc:`/extensions/pyt/directives` for all available directives.

2. **Execution Function**

   .. code-block:: python

      def main():
          # Test logic here

   The ``main()`` function contains your test logic. Canary:

   - Calls this function when executing the test
   - Captures stdout/stderr
   - Records the exit code (0 = success, non-zero = failure)
   - Measures execution time

3. **Entry Point**

   .. code-block:: python

      if __name__ == "__main__":
          main()
   
   This standard Python pattern ensures the test runs when executed directly.

Accessing Test Information
--------------------------

The ``canary.get_instance()`` function provides access to test metadata:

.. code-block:: python

   instance = canary.get_instance()
   
   # Common instance properties
   print(f"Name: {instance.name}")      # Test name
   print(f"ID: {instance.id}")         # Unique identifier
   print(f"Path: {instance.path}")     # Filesystem path
   print(f"Parameters: {instance.parameters}")  # Parameter values

Test Lifecycle
--------------

When you run ``canary run minimal.pyt``:

1. **Discovery**: Canary finds ``.pyt`` files
2. **Generation**: Creates a JobSpec from the test file
3. **Execution**: Runs the test in a controlled environment
4. **Persistence**: Stores results in the workspace
5. **Reporting**: Creates user-facing views

Understanding Status Codes
--------------------------

Canary tests can have several outcomes:

- **SUCCESS**: Exit code 0, no exceptions
- **FAILED**: Non-zero exit code or unhandled exception
- **TIMEOUT**: Test exceeded timeout
- **SKIPPED**: Test was skipped due to conditions

.. code-block:: python
   :caption: Demonstrating different outcomes

   # Success
   def test_pass():
       print("All good!")  # Exit code 0
   
   # Failure
   def test_fail():
       raise ValueError("Something went wrong")  # Non-zero exit
   
   # Conditional skip
   def test_skip():
       import canary_pyt
       canary_pyt.directives.skip("Not needed for this run")

Best Practices for Basic Tests
------------------------------

1. **Keep tests focused**: One test = one logical unit
2. **Use descriptive names**: ``test_addition.pyt`` > ``test1.pyt``
3. **Add keywords**: Helps with filtering and organization
4. **Include descriptions**: Documents test purpose
5. **Validate explicitly**: Check conditions and raise exceptions
6. **Use instance data**: Access test metadata when needed

.. seealso::

   - :doc:`test-structure`: Detailed test anatomy
   - :doc:`running-tests`: How to run and manage tests
   - :doc:`status-codes`: Complete status reference
   - :doc:`/extensions/pyt/directives`: All available directives