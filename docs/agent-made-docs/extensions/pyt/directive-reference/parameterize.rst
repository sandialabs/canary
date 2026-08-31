.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

parameterize
============

.. currentmodule:: canary_pyt.directives

.. autofunction:: parameterize

Purpose
-------

Define parameter sets for test variants. This directive creates multiple test instances with different parameter combinations.

Parameters
----------

:param name: Parameter name (string)
:param values: Parameter values (list, tuple, or parameter space object)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Creates multiple job variants based on parameter values
- Job names include parameter name and value: ``test[name=value]``
- Multiple ``parameterize`` directives combine using Cartesian product
- Parameter values are accessible via ``instance.parameters`` at runtime

When
----

- **Affects**: Discovery and generation phases
- **Runtime**: Parameter values accessible via ``canary.get_instance().parameters``

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.parameterize(
       "size",
       [10, 20, 30],
       when="-o extended"
   )

Examples
--------

**Simple Parameterization**:

.. code-block:: python

   canary_pyt.directives.parameterize("size", [10, 20, 30])

Generates 3 jobs:

- ``test[size=10]``
- ``test[size=20]``
- ``test[size=30]``

**Multiple Parameterization**:

.. code-block:: python

   canary_pyt.directives.parameterize("size", [10, 20])
   canary_pyt.directives.parameterize("mode", ["fast", "slow"])

Generates 4 jobs (Cartesian product):

- ``test[size=10,mode=fast]``
- ``test[size=10,mode=slow]``
- ``test[size=20,mode=fast]``
- ``test[size=20,mode=slow]``

**Parameter Space Objects**:

.. code-block:: python

   from _canary.paramset import ListParameterSpace

   canary_pyt.directives.parameterize(
       "value",
       ListParameterSpace([1, 2, 3])
   )

**Conditional Parameterization**:

.. code-block:: python

   canary_pyt.directives.parameterize(
       "extended_param",
       ["a", "b", "c"],
       when="-o extended"
   )

Edge Cases
----------

**Empty Parameter List**:

.. code-block:: python

   canary_pyt.directives.parameterize("empty", [])  # No jobs generated

**Single Parameter Value**:

.. code-block:: python

   canary_pyt.directives.parameterize("single", [42])  # 1 job

**Duplicate Parameter Names**:

.. code-block:: python

   canary_pyt.directives.parameterize("param", [1, 2])
   canary_pyt.directives.parameterize("param", [3, 4])  # Error!

Notes
-----

- Parameter names must be valid Python identifiers
- Parameter values must be JSON-serializable
- Parameter combinations are reduced to unique sets
- Resource-consuming parameters (``cpus``, ``gpus``, ``nodes``) should use dedicated directives

See Also
--------

- :doc:`../parameterization`: Parameterization overview
- :doc:`cpus`: CPU resource directive
- :doc:`gpus`: GPU resource directive
- :doc:`nodes`: Node resource directive
