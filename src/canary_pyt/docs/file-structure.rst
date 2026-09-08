.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.pyt File Structure
===================

Recommended `.pyt` file organization ensures proper discovery, generation, and execution.

Basic Structure
---------------

A well-structured `.pyt` file follows this pattern:

.. code-block:: python

   # 1. Imports (standard library, third-party, Canary)
   import canary
   import canary_pyt

   # 2. Directives (test metadata, requirements, configuration)
   canary_pyt.directives.keywords("smoke")
   canary_pyt.directives.parameterize("size", [10, 20, 30])
   canary_pyt.directives.timeout(60)

   # 3. Test function definition
   def main():
       # Test logic here
       instance = canary.get_instance()
       size = instance.parameters.size
       # ... test implementation ...

   # 4. Runtime guard
   if __name__ == "__main__":
       main()

Import Guidelines
-----------------

**Required Imports**:

.. code-block:: python

   import canary                  # Runtime access to test instance
   import canary_pyt              # Directive namespace

**Optional Imports**:

.. code-block:: python

   import sys                     # Platform detection
   import os                      # File path manipulation
   import math                    # Mathematical operations
   # Other standard library modules as needed

**Avoid**:

- Importing modules with side effects at import time
- Importing test frameworks that conflict with Canary's execution model
- Using `from canary_pyt.directives import *` (explicit imports only)

Directive Placement
-------------------

**Best Practices**:

1. **Module Level**: Directives must appear at module level, not inside functions or classes
2. **Before Test Logic**: Place all directives before function definitions
3. **Group Related Directives**: Keep related directives together for readability

Test Function Definition
------------------------

**Recommended Pattern**:

.. code-block:: python

   def main():
       """Main test function."""
       instance = canary.get_instance()
       # Access parameters, resources, etc.
       # Implement test logic
       # Raise exceptions on failure

**Alternative Patterns**:

.. code-block:: python

   def test_<feature>():
       """Feature-specific test."""
       # Test implementation

   def run():
       """Alternative entry point."""
       # Test logic

Runtime Guard
-------------

**Required**: Always guard test execution with ``if __name__ == "__main__"``:

.. code-block:: python

   if __name__ == "__main__":
       main()

**Why**:

- Prevents test execution during discovery phase
- Allows Canary to record directives before running tests
- Enables standalone execution for debugging

No Side Effects During Discovery
---------------------------------

**Safe During Discovery**:

.. code-block:: python

   # These are OK - just definitions
   import canary
   import canary_pyt

   canary_pyt.directives.keywords("unit")

   def test_function():
       pass

**Unsafe During Discovery**:

.. code-block:: python

   # AVOID - side effects at import time
   import sys
   print("Loading test")  # Side effect!

   data = open("file.txt").read()  # Side effect!

   class TestClass:  # Complex definitions may have side effects
       def __init__(self):
           # ...

Test Instance Access
--------------------

Access the test instance at runtime using ``canary.get_instance()``:

.. code-block:: python

   def main():
       instance = canary.get_instance()

       # Access test metadata
       print(f"Test name: {instance.name}")
       print(f"Keywords: {instance.keywords}")
       print(f"Parameters: {instance.parameters}")

       # Access resources
       print(f"CPUs: {instance.cpu_ids}")
       print(f"GPUs: {instance.gpu_ids}")

       # Access workspace
       print(f"Working directory: {instance.working_directory}")

**Common Instance Attributes**:

- ``name``: Test name
- ``keywords``: List of keywords
- ``parameters``: Parameter dictionary
- ``cpu_ids``: List of CPU IDs
- ``gpu_ids``: List of GPU IDs
- ``timeout``: Timeout in seconds
- ``working_directory``: Execution workspace
- ``sources``: Source files

See :doc:`test-instance` for complete reference.

Example: Complete .pyt File
---------------------------

.. code-block:: python

   """"""""""""""""""""""""""""""""""""""""""
   Example test demonstrating best practices.
   """"""""""""""""""""""""""""""""""""""""""

   # Standard library imports
   import os
   import sys

   # Canary imports
   import canary
   import canary_pyt

   # Test configuration (directives)
   canary_pyt.directives.keywords("example", "demo")
   canary_pyt.directives.timeout(120)
   canary_pyt.directives.cpus(4)

   # Test implementation
   def main():
       """Main test function."""
       instance = canary.get_instance()

       print(f"Starting {instance.name}")
       print(f"Keywords: {instance.keywords}")
       print(f"Timeout: {instance.timeout}s")

       # Test logic here
       result = perform_test()

       if not result:
           raise RuntimeError("Test failed!")

       print("Test passed!")

   def perform_test():
       """Helper function."""
       return True

   # Runtime guard
   if __name__ == "__main__":
       main()

See Also
--------

- :doc:`overview`: Introduction to canary_pyt
- :doc:`directives`: Available directives
- :doc:`test-instance`: TestInstance API reference
- :doc:`patterns`: Common patterns and examples
