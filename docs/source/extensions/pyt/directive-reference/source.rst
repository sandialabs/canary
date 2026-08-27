.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

source
======

.. currentmodule:: canary_pyt.directives

.. autofunction:: source

Purpose
-------

Source a shell script to set up the runtime environment. This directive is used to execute shell commands before test execution.

Parameters
----------

:param name: Shell script name (string)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Sources shell script before execution
- Affects runtime environment
- Script is executed in shell
- Used for environment setup

When
----

- **Affects**: Generation phase
- **Runtime**: Script sourced during setup

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.source(
       "setup.sh",
       when="platform=linux"
   )

Examples
--------

**Source Setup Script**:

.. code-block:: python

   canary_pyt.directives.source("setup.sh")

**Source Environment Script**:

.. code-block:: python

   canary_pyt.directives.source("env.sh")

**Conditional Source**:

.. code-block:: python

   canary_pyt.directives.source("gpu_setup.sh", when="gpus>0")

Edge Cases
----------

**Non-Existent Script**:

.. code-block:: python

   canary_pyt.directives.source("missing.sh")  # Error at runtime

**Empty Script Name**:

.. code-block:: python

   canary_pyt.directives.source("")  # Error

Notes
-----

- Script sourcing is backend-specific
- Script is executed in shell
- Used for environment setup
- Script failures may affect test execution
- Use ``load_module`` for environment modules

Comparison with load_module
---------------------------

**source**:

.. code-block:: python

   canary_pyt.directives.source("setup.sh")  # Shell script

**load_module**:

.. code-block:: python

   canary_pyt.directives.load_module("gcc")  # Environment module

Best Practices
--------------

1. **Environment Setup**:

   .. code-block:: python

      canary_pyt.directives.source("env.sh")

2. **Conditional**:

   .. code-block:: python

      canary_pyt.directives.source("setup.sh", when="-o setup")

See Also
--------

- :doc:`load_module`: Load module directive
- :doc:`preload`: Preload directive
- :doc:`../execution-model`: Execution model
