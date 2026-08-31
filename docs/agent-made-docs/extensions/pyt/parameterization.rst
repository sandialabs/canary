.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Parameterization
================

Parameterization enables test variant generation by combining parameter values. This is a core feature of ``canary_pyt`` that allows comprehensive test coverage with minimal code duplication.

Parameter Space Types
---------------------

**List Parameter Space**

Simple list of values:

.. code-block:: python

   canary_pyt.directives.parameterize("size", [10, 20, 30])

**Centered Parameter Space**

Values centered around a midpoint:

.. code-block:: python

   from _canary.paramset import CenteredParameterSpace

   canary_pyt.directives.parameterize(
       "offset",
       CenteredParameterSpace(center=0, spread=2, num=5)
   )

**Random Parameter Space**

Randomly sampled values:

.. code-block:: python

   from _canary.paramset import RandomParameterSpace

   canary_pyt.directives.parameterize(
       "value",
       RandomParameterSpace(min=0, max=100, num=10, seed=42)
   )

**Samples Parameter Space**

Explicit samples:

.. code-block:: python

   from _canary.paramset import SamplesParameterSpace

   canary_pyt.directives.parameterize(
       "config",
       SamplesParameterSpace(["a", "b", "c"])
   )

Parameter Combination
---------------------

Multiple ``parameterize`` directives combine using Cartesian product:

.. code-block:: python

   canary_pyt.directives.parameterize("size", [10, 20])
   canary_pyt.directives.parameterize("mode", ["fast", "slow"])

Generates 4 jobs:

- ``test[size=10,mode=fast]``
- ``test[size=10,mode=slow]``
- ``test[size=20,mode=fast]``
- ``test[size=20,mode=slow]``

Parameter Access
----------------

Access parameters at runtime via ``instance.parameters``:

.. code-block:: python

   def main():
       instance = canary.get_instance()
       size = instance.parameters.size
       mode = instance.parameters.mode
       print(f"Running with size={size}, mode={mode}")

Example: Running Parameterized Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. doc-run::
   :before_script: [copy-examples]
   :script: [python3 -m canary describe ./parameterize/parameterize1.pyt, python3 -m canary run ./parameterize/parameterize1.pyt, python3 -m canary status -rA]
   :cwd: /examples

This example shows how to inspect, run, and check status of parameterized tests.

Named Variants
--------------

Parameterized jobs create named variants:

.. code-block:: text

   test[size=10]          # size parameter
   test[mode=fast]         # mode parameter
   test[size=10,mode=fast] # both parameters

Resource Parameters
-------------------

**Fixed Resources**:

.. code-block:: python

   canary_pyt.directives.cpus(4)  # Fixed 4 CPUs, no variant

**Parameterized Resources**:

.. code-block:: python

   canary_pyt.directives.parameterize("cpus", [2, 4, 8])
   # Generates: test[cpus=2], test[cpus=4], test[cpus=8]

Parameter Set Operations
------------------------

**Combine**:

.. code-block:: python

   # Multiple parameterize calls combine
   canary_pyt.directives.parameterize("a", [1, 2])
   canary_pyt.directives.parameterize("b", [3, 4])
   # Result: 4 combinations

**Reduce**:

.. code-block:: python

   # Duplicate combinations are removed
   canary_pyt.directives.parameterize("x", [1, 2])
   canary_pyt.directives.parameterize("x", [2, 3])
   # Result: [1, 2, 3] (unique values)

Advanced Parameterization
-------------------------

**Conditional Parameterization**:

.. code-block:: python

   canary_pyt.directives.parameterize(
       "extended",
       ["a", "b"],
       when="-o extended"
   )

**Parameter-Based Activation**:

.. code-block:: python

   canary_pyt.directives.parameterize("size", [10, 20])
   canary_pyt.directives.keywords(
       "large",
       when="parameters[size]=20"
   )

**Nested Parameterization**:

.. code-block:: python

   sizes = [10, 20, 30]
   modes = ["fast", "slow"]

   for size in sizes:
       for mode in modes:
           canary_pyt.directives.parameterize(
               f"config_{size}_{mode}",
               [f"{size}-{mode}"]
           )

Best Practices
--------------

1. **Use Descriptive Names**:

   .. code-block:: python

      canary_pyt.directives.parameterize("workload_size", [10, 20, 30])

2. **Limit Combinations**:

   .. code-block:: python

      # Too many combinations
      canary_pyt.directives.parameterize("a", [1, 2, 3, 4, 5])
      canary_pyt.directives.parameterize("b", [1, 2, 3, 4, 5])
      # 25 jobs!

3. **Use Conditional Activation**:

   .. code-block:: python

      canary_pyt.directives.parameterize(
          "extended_param",
          ["a", "b", "c"],
          when="-o extended"
      )

4. **Document Complex Parameterization**:

   .. code-block:: python

      # Performance testing matrix
      # size: workload size
      # threads: number of threads
      canary_pyt.directives.parameterize("size", [100, 1000, 10000])
      canary_pyt.directives.parameterize("threads", [1, 2, 4])

Edge Cases
----------

**Empty Parameter List**:

.. code-block:: python

   canary_pyt.directives.parameterize("empty", [])  # No jobs generated

**Single Value**:

.. code-block:: python

   canary_pyt.directives.parameterize("single", [42])  # 1 job

**Duplicate Names**:

.. code-block:: python

   canary_pyt.directives.parameterize("param", [1, 2])
   canary_pyt.directives.parameterize("param", [3, 4])  # Error!

**Non-Serializable Values**:

.. code-block:: python

   canary_pyt.directives.parameterize("func", [lambda x: x])  # Error!

See Also
--------

- :doc:`directive-reference/parameterize`: parameterize directive reference
- :doc:`directive-reference/cpus`: cpus directive
- :doc:`directive-reference/gpus`: gpus directive
- :doc:`directive-reference/nodes`: nodes directive
- :doc:`patterns`: Parameterization patterns
