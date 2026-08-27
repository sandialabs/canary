.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-example-parameterized:

Parameterized Test Example
==========================

This example demonstrates parameterized testing, where a single test definition
generates multiple test instances with different parameters.

Complete Example Code
---------------------

.. literalinclude:: param_test.pyt
   :language: python
   :caption: param_test.pyt

This example demonstrates parameterized testing with Canary.

Running the Example
-------------------

Let's execute this parameterized test:

.. doc-run::
   :before_script: ['cp ${doc_source_dir}/param_test.pyt .', 'python3 -m canary init']
   :script: ['python3 -m canary run param_test.pyt']
   :display: command, stdout, stderr

How Parameterization Works
--------------------------

When you run this test, Canary:

1. **Generates instances**: Creates 5×5 = 25 test instances (all combinations)
2. **Names instances**: ``param_test[a=1,b=1]``, ``param_test[a=1,b=2]``, etc.
3. **Runs independently**: Each instance executes separately
4. **Collects results**: All results are available in the workspace

Running the Example
-------------------

.. code-block:: console

   # Run all parameterized instances
   python3 -m canary run param_test.pyt

    # Run tests with specific parameter values
    python3 -m canary run -p "a=2" param_test.pyt
    python3 -m canary run -p "b=5" param_test.pyt

   # View all results
   python3 -m canary status -rA

Parameterization Patterns
-------------------------

Single Parameter
^^^^^^^^^^^^^^^^

.. code-block:: python

   canary_pyt.directives.parameterize("size", [[10], [100], [1000]])

Multiple Parameters
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   canary_pyt.directives.parameterize(
       "method,dataset", [("fast", "small"), ("accurate", "large")]
   )

Parameter Types
^^^^^^^^^^^^^^^

.. code-block:: python

   # Numbers
   canary_pyt.directives.parameterize("iterations", [[10], [50], [100]])
    
   # Strings
   canary_pyt.directives.parameterize("algorithm", [["bfs"], ["dfs"], ["astar"]])
   
   # Booleans
   canary_pyt.directives.parameterize("use_cache", [True, False])
   
   # Mixed types
   canary_pyt.directives.parameterize(
       "optimizer", ["adam", "sgd"],
       "learning_rate", [0.01, 0.001, 0.0001]
   )

Advanced Parameterization
-------------------------

Conditional Parameterization
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   canary_pyt.directives.parameterize("size", [10, 100])
   canary_pyt.directives.parameterize("method", ["fast", "slow"])
   
   # Only run large tests with fast method
   canary_pyt.directives.parameterize(
       "size", [1000],
       "method", ["fast"],
       when="size==1000 and method=='fast'"
   )

Parameter Constraints
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   canary_pyt.directives.parameterize("a", range(10))
   canary_pyt.directives.parameterize("b", range(10))
   
   # Only run when a < b
   def main():
       instance = canary.get_instance()
       if instance.parameters.a >= instance.parameters.b:
           instance.skip("a must be less than b")
           return

Parameter Files
^^^^^^^^^^^^^^^^

.. code-block:: python

   # Load parameters from JSON file
   import json
   
   with open("parameters.json") as f:
       params = json.load(f)
   
   canary_pyt.directives.parameterize(
       "config", params["configurations"]
   )

Best Practices
--------------

1. **Start small**: Begin with a few parameter values
2. **Name clearly**: Use descriptive parameter names
3. **Validate combinations**: Check for invalid parameter mixes
4. **Limit scope**: Use ``when`` clauses to reduce test matrix
5. **Measure results**: Record measurements for analysis
6. **Document purpose**: Explain what each parameter controls

Common Use Cases
----------------

**Algorithm Comparison**

.. code-block:: python

   canary_pyt.directives.parameterize(
       "algorithm", ["quicksort", "mergesort", "heapsort"],
       "size", [1000, 10000, 100000]
   )

**Configuration Testing**

.. code-block:: python

   canary_pyt.directives.parameterize(
       "threads", [1, 2, 4, 8],
       "chunk_size", [100, 1000, 10000]
   )

**Data Sensitivity Analysis**

.. code-block:: python

   canary_pyt.directives.parameterize(
       "noise_level", [0.0, 0.1, 0.5, 1.0],
       "iterations", [10, 50, 100]
   )

.. seealso::

   - :doc:`/tutorial/intermediate/parameterization`: Parameterization tutorial
   - :doc:`/extensions/pyt/parameterization`: Complete parameterization reference
   - :doc:`/user/selection`: Filtering parameterized tests
   - :doc:`/tutorial/examples/composite`: Composite analysis with parameterization