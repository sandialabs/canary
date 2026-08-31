.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Patterns
========

Common patterns for authoring `.pyt` files. These patterns demonstrate best practices for organizing tests, managing dependencies, and handling resources.

Basic Test Pattern
------------------

Simple test with metadata:

.. code-block:: python

   import canary
   import canary_pyt

   # Metadata
   canary_pyt.directives.keywords("smoke", "unit")
   canary_pyt.directives.timeout(30)

   # Test logic
   def main():
       instance = canary.get_instance()
       print(f"Running {instance.name}")
       assert True

   if __name__ == "__main__":
       main()

Parameterized Test Pattern
---------------------------

Test with parameterization:

.. code-block:: python

   import canary
   import canary_pyt

   # Parameterization
   canary_pyt.directives.parameterize("size", [10, 20, 30])
   canary_pyt.directives.keywords("parametric")

   # Test logic
   def main():
       instance = canary.get_instance()
       size = instance.parameters.size
       print(f"Running with size={size}")
       assert size in [10, 20, 30]

   if __name__ == "__main__":
       main()

Dependency Pattern
------------------

Test with dependencies:

.. code-block:: python

   import canary
   import canary_pyt

   # Dependencies
   canary_pyt.directives.depends_on("setup_database")
   canary_pyt.directives.keywords("integration")

   # Test logic
   def main():
       instance = canary.get_instance()
       print(f"Running {instance.name}")
       # Test logic here

   if __name__ == "__main__":
       main()

Resource Pattern
----------------

Test with resource requirements:

.. code-block:: python

   import canary
   import canary_pyt

   # Resources
   canary_pyt.directives.cpus(4)
   canary_pyt.directives.gpus(1)
   canary_pyt.directives.keywords("performance")

   # Test logic
   def main():
       instance = canary.get_instance()
       print(f"CPUs: {instance.cpu_ids}")
       print(f"GPUs: {instance.gpu_ids}")
       # Performance test logic

   if __name__ == "__main__":
       main()

Asset Pattern
-------------

Test with assets:

.. code-block:: python

   import canary
   import canary_pyt

   # Assets
   canary_pyt.directives.copy("test_data.csv")
   canary_pyt.directives.copy("config.json")
   canary_pyt.directives.keywords("data")

   # Test logic
   def main():
       # Read copied files
       with open("test_data.csv", "r") as f:
           data = f.read()
       # Test logic here

   if __name__ == "__main__":
       main()

Artifact Pattern
----------------

Test with artifacts:

.. code-block:: python

   import canary
   import canary_pyt

   # Artifacts
   canary_pyt.directives.artifact("output.txt")
   canary_pyt.directives.artifact("*.log")
   canary_pyt.directives.keywords("output")

   # Test logic
   def main():
       # Generate output
       with open("output.txt", "w") as f:
           f.write("Test results")
       # Test logic here

   if __name__ == "__main__":
       main()

Baseline Pattern
----------------

Test with baselines:

.. code-block:: python

   import canary
   import canary_pyt

   # Baselines
   canary_pyt.directives.baseline("output.txt")
   canary_pyt.directives.keywords("regression")

   # Test logic
   def main():
       # Generate output
       with open("output.txt", "w") as f:
           f.write("Test results")
       # Test logic here

   if __name__ == "__main__":
       main()

Expected Failure Pattern
------------------------

Test with expected failure:

.. code-block:: python

   import canary
   import canary_pyt

   # Expected failure
   canary_pyt.directives.xfail(code=1)
   canary_pyt.directives.keywords("known_issue")

   # Test logic
   def main():
       # This test is expected to fail
       raise RuntimeError("Expected failure")

   if __name__ == "__main__":
       main()

Composite Analysis Pattern
---------------------------

Composite analysis job:

.. code-block:: python

   import canary
   import canary_pyt

   # Composite analysis
   canary_pyt.directives.aggregate(
       "analyze_results",
       ["test1", "test2", "test3"]
   )
   canary_pyt.directives.keywords("analysis")

   # Analysis logic
   def main():
       instance = canary.get_instance()

       # Access child results
       results = []
       for child_name in ["test1", "test2", "test3"]:
           child = instance.get_dependency(child_name)
           results.append(child.returncode)

       # Aggregate results
       print(f"Results: {results}")

   if __name__ == "__main__":
       main()

Conditional Activation Pattern
-------------------------------

Test with conditional activation:

.. code-block:: python

   import canary
   import canary_pyt

   # Conditional activation
   canary_pyt.directives.keywords("extended", when="-o extended")
   canary_pyt.directives.timeout(120, when="keywords=extended")

   # Test logic
   def main():
       instance = canary.get_instance()
       if "extended" in instance.keywords:
           print("Running extended test")
       else:
           print("Running basic test")

   if __name__ == "__main__":
       main()

Best Practices
--------------

1. **Organize Directives**:
   - Group related directives together
   - Place directives at module level
   - Keep test logic separate

2. **Use Canonical Namespace**:
   - Always use ``canary_pyt.directives``
   - Avoid deprecated ``canary.directives``

3. **Guard Test Logic**:
   - Use ``if __name__ == "__main__"``
   - Prevent execution during discovery

4. **Access Instance**:
   - Use ``canary.get_instance()`` for runtime data
   - Access parameters, resources, dependencies

5. **Document Complex Logic**:
   - Add comments for complex directives
   - Explain non-obvious behavior

See Also
--------

- :doc:`file-structure`: File organization
- :doc:`directives`: Directives overview
- :doc:`directive-reference/index`: Directive reference
- :doc:`patterns`: Common patterns
