.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Limitations
===========

Understanding the limitations of ``canary_pyt`` helps avoid common pitfalls and ensures proper test authoring.

Discovery Phase Execution
-------------------------

**.pyt files are executed during discovery**:

- Directives are recorded during file scanning
- Test functions are defined but not executed
- ``__name__ == "__load__"`` during discovery
- ``__name__ == "__main__"`` during execution

**Implication**: Avoid side effects at import/discovery time.

Avoid Side Effects
------------------

**Bad**: Side effects during discovery

.. code-block:: python

   # BAD - Side effect at import time
   print("Loading test")  # Executes during discovery
   data = open("file.txt").read()  # Executes during discovery

**Good**: No side effects during discovery

.. code-block:: python

   # GOOD - Only definitions
   import canary
   import canary_pyt

   canary_pyt.directives.keywords("unit")

   def test_function():
       pass  # No execution during discovery

Canonical Namespace
--------------------

**Canonical namespace**: ``canary_pyt.directives``

.. code-block:: python

   # GOOD - Canonical namespace
   import canary_pyt
   canary_pyt.directives.keywords("smoke")

**Deprecated namespace**: ``canary.directives``

.. code-block:: python

   # BAD - Deprecated namespace
   import canary
   canary.directives.keywords("smoke")  # Avoid

Fixed Resources
---------------

**Fixed resources do not affect job names**:

.. code-block:: python

   canary_pyt.directives.cpus(4)  # No variant name added
   canary_pyt.directives.gpus(1)  # No variant name added

**Implication**: Use ``parameterize`` to create named variants.

.. code-block:: python

   canary_pyt.directives.parameterize("cpus", [2, 4, 8])  # Creates variants

Random Parameter Spaces
-----------------------

**Random spaces should use fixed seed**:

.. code-block:: python

   # GOOD - Fixed seed for reproducibility
   from _canary.paramset import RandomParameterSpace
   canary_pyt.directives.parameterize(
       "value",
       RandomParameterSpace(min=0, max=100, num=10, seed=42)
   )

**Implication**: Ensures reproducible test runs.

Module and Source Behavior
---------------------------

**Module/source behavior depends on environment**:

.. code-block:: python

   canary_pyt.directives.load_module("gcc")  # Requires environment modules
   canary_pyt.directives.source("setup.sh")  # Requires shell

**Implication**: May not work in all execution backends.

Explicit IDs
------------

**Explicit IDs must be valid and unique**:

.. code-block:: python

   # GOOD - Valid ID
   canary_pyt.directives.set_id("test_001")

   # BAD - Invalid ID
   canary_pyt.directives.set_id("invalid id")  # Error

**Implication**: IDs must follow SHA-like format and be unique.

Preload Limitations
-------------------

**Preload may have limited effect**:

.. code-block:: python

   canary_pyt.directives.preload("data.csv")  # May not preload

**Implication**: Effect depends on execution backend.

Include Limitations
-------------------

**Include may have limited functionality**:

.. code-block:: python

   canary_pyt.directives.include("common.pyt")  # May not include

**Implication**: Effect depends on backend and file type.

Edge Cases
----------

**Empty parameter list**:

.. code-block:: python

   canary_pyt.directives.parameterize("empty", [])  # No jobs generated

**Single parameter value**:

.. code-block:: python

   canary_pyt.directives.parameterize("single", [42])  # 1 job

**Duplicate parameter names**:

.. code-block:: python

   canary_pyt.directives.parameterize("param", [1, 2])
   canary_pyt.directives.parameterize("param", [3, 4])  # Error

**Non-serializable parameter values**:

.. code-block:: python

   canary_pyt.directives.parameterize("func", [lambda x: x])  # Error

Best Practices
--------------

1. **Avoid side effects during discovery**:
   - No I/O operations at module level
   - No function calls at module level
   - Only directive definitions

2. **Use canonical namespace**:
   - Always use ``canary_pyt.directives``
   - Avoid deprecated ``canary.directives``

3. **Use parameterize for variants**:
   - Fixed resources: ``cpus(N)``, ``gpus(N)``, ``nodes(N)``
   - Parameterized resources: ``parameterize("cpus", [...])``

4. **Use fixed seeds for random spaces**:
   - Ensures reproducibility
   - Avoids flaky tests

5. **Check backend support**:
   - ``load_module``, ``source``, ``preload``, ``include``
   - May not work in all backends

6. **Use valid explicit IDs**:
   - SHA-like format
   - Unique across test suite
   - No special characters

See Also
--------

- :doc:`file-structure`: File organization
- :doc:`directives`: Directives overview
- :doc:`directive-reference/index`: Directive reference
- :doc:`patterns`: Common patterns
