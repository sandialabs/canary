.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

depends_on
==========

.. currentmodule:: canary_pyt.directives

.. autofunction:: depends_on

Purpose
-------

Define dependencies between jobs. This directive specifies that the current job depends on other jobs completing before it can run.

Parameters
----------

:param \*arg: Dependency selectors (string or dict)
:param when: Optional conditional activation (WhenType)
:param \*\*kwargs: Additional dependency options

Effect on Generated Jobs
------------------------

- Creates dependency edges in the job graph
- Current job waits for dependent jobs to complete
- Affects job scheduling order
- Supports result-sensitive execution via ``expects`` and ``when``

When
----

- **Affects**: Generation phase (dependency graph construction)
- **Runtime**: Dependency resolution during execution

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.depends_on(
       "setup_test",
       when="always"
   )

Examples
--------

**Simple Dependency**:

.. code-block:: python

   canary_pyt.directives.depends_on("setup_test")

**Multiple Dependencies**:

.. code-block:: python

   canary_pyt.directives.depends_on("setup_test", "prepare_data")

**Dictionary Form**:

.. code-block:: python

   canary_pyt.directives.depends_on(
       {"job": "setup_test", "when": "on_success"}
   )

**Result-Sensitive Execution**:

.. code-block:: python

   canary_pyt.directives.depends_on(
       "setup_test",
       expects="success"
   )

**Parameter Substitution**:

.. code-block:: python

   canary_pyt.directives.parameterize("size", ["small", "large"])
   canary_pyt.directives.depends_on("setup_{size}")

Generates dependencies:

- ``test[size=small]`` depends on ``setup_small``
- ``test[size=large]`` depends on ``setup_large``

**Glob Pattern Matching**:

.. code-block:: python

   canary_pyt.directives.depends_on("setup_*")

Edge Cases
----------

**Circular Dependencies**:

.. code-block:: python

   # test1.pyt
   canary_pyt.directives.depends_on("test2")

   # test2.pyt
   canary_pyt.directives.depends_on("test1")  # Error: Circular dependency!

**Missing Dependencies**:

.. code-block:: python

   canary_pyt.directives.depends_on("nonexistent_test")  # Warning/Error

**Self Dependency**:

.. code-block:: python

   canary_pyt.directives.depends_on("test")  # Depends on itself - Error!

Notes
-----

- Dependency selectors are resolved at generation time
- Dependencies can span multiple `.pyt` files
- Composite analysis jobs automatically depend on their children
- Use ``when`` parameter to control when dependency applies

Supported Dependency Options
----------------------------

**job**: Job name or pattern to depend on

**when**: When to apply dependency (``on_success``, ``on_failure``, ``always``)

**expects**: Expected outcome (``success``, ``failure``, ``any``)

See Also
--------

- :doc:`../dependencies`: Dependencies overview
- :doc:`aggregate`: Composite analysis
- :doc:`../conditional-activation`: When expressions
