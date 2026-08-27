.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

preload
=======

.. currentmodule:: canary_pyt.directives

.. autofunction:: preload

Purpose
-------

Preload data or modules before test execution. This directive is used to load data into memory or set up the environment before the test runs.

Parameters
----------

:param arg: Data or module to preload (string)
:param when: Optional conditional activation (WhenType)
:param source: Whether to source as shell script (bool, default: False)

Effect on Generated Jobs
------------------------

- Preloads data or modules before execution
- Affects runtime environment
- May have limited or no effect depending on backend
- Used for performance optimization

When
----

- **Affects**: Generation phase
- **Runtime**: Preloading during setup

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.preload(
       "data.csv",
       when="-o preload"
   )

Examples
--------

**Preload Data**:

.. code-block:: python

   canary_pyt.directives.preload("dataset.csv")

**Preload Module**:

.. code-block:: python

   canary_pyt.directives.preload("mymodule")

**Preload as Source**:

.. code-block:: python

   canary_pyt.directives.preload("setup.sh", source=True)

Edge Cases
----------

**Non-Existent File**:

.. code-block:: python

   canary_pyt.directives.preload("missing.dat")  # Warning/Error

**Empty Argument**:

.. code-block:: python

   canary_pyt.directives.preload("")  # Error

Notes
-----

- Preloading behavior is backend-specific
- May have limited effect in some environments
- Use for performance optimization
- ``source=True`` sources as shell script
- Preloading may not be supported in all backends

Best Practices
--------------

1. **Large Datasets**:

   .. code-block:: python

      canary_pyt.directives.preload("large_dataset.csv")

2. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.preload("data.csv", when="-o preload")

See Also
--------

- :doc:`load_module`: Load module directive
- :doc:`source`: Source directive
- :doc:`../execution-model`: Execution model
