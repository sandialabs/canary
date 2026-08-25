.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

load_module
===========

.. currentmodule:: canary_pyt.directives

.. autofunction:: load_module

Purpose
-------

Load environment modules before test execution. This directive is used to set up the runtime environment by loading modules (e.g., environment modules on HPC systems).

Parameters
----------

:param name: Module name (string)
:param use: Optional module use specification (string)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Loads environment module before execution
- Affects runtime environment
- Module availability is backend-specific
- Used primarily in HPC environments

When
----

- **Affects**: Generation phase
- **Runtime**: Module loaded during setup

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.load_module(
       "gcc",
       when="platform=linux"
   )

Examples
--------

**Simple Module**:

.. code-block:: python

   canary_pyt.directives.load_module("gcc")

**Module with Version**:

.. code-block:: python

   canary_pyt.directives.load_module("gcc/11.2.0")

**Module with Use**:

.. code-block:: python

   canary_pyt.directives.load_module("gcc", use="/path/to/modules")

**Conditional Module**:

.. code-block:: python

   canary_pyt.directives.load_module("cuda", when="gpus>0")

Edge Cases
----------

**Non-Existent Module**:

.. code-block:: python

   canary_pyt.directives.load_module("nonexistent")  # Error at runtime

**Empty Module Name**:

.. code-block:: python

   canary_pyt.directives.load_module("")  # Error

Notes
-----

- Module loading is backend-specific
- Primarily used in HPC environments with environment modules
- Module availability affects test execution
- Use ``source`` for shell-based environment setup
- Module loading may fail if module is not available

Comparison with source
----------------------

**load_module**:

.. code-block:: python

   canary_pyt.directives.load_module("gcc")  # Environment modules

**source**:

.. code-block:: python

   canary_pyt.directives.source("setup.sh")  # Shell script

Best Practices
--------------

1. **Compiler Modules**:

   .. code-block:: python

      canary_pyt.directives.load_module("gcc/11.2.0")

2. **Library Modules**:

   .. code-block:: python

      canary_pyt.directives.load_module("cuda/11.4")

3. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.load_module("mpi", when="-o mpi")

See Also
--------

- :doc:`source`: Source directive
- :doc:`preload`: Preload directive
- :doc:`../execution-model`: Execution model
