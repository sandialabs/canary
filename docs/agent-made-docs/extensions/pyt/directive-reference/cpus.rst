.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

cpus
====

.. currentmodule:: canary_pyt.directives

.. autofunction:: cpus

Purpose
-------

Set the fixed CPU resource requirement for a job. This directive specifies the number of CPUs required to execute the job.

Parameters
----------

:param arg: Number of CPUs (int)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Sets a fixed CPU resource meta-parameter
- Does NOT create named job variants (unlike ``parameterize("cpus", ...)``)
- CPU requirement is enforced by the resource pool
- Accessible via ``instance.cpu_ids`` at runtime

When
----

- **Affects**: Generation phase
- **Runtime**: CPU allocation during execution

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.cpus(4, when="-o high_performance")

Examples
--------

**Fixed CPU Requirement**:

.. code-block:: python

   canary_pyt.directives.cpus(4)  # Requires 4 CPUs

**Conditional CPU Requirement**:

.. code-block:: python

   canary_pyt.directives.cpus(8, when="keywords=performance")

**Multiple CPU Directives**:

.. code-block:: python

   canary_pyt.directives.cpus(2)  # Default
   canary_pyt.directives.cpus(4, when="-o extended")  # Override

Comparison with parameterize
----------------------------

**Fixed CPUs (this directive)**:

.. code-block:: python

   canary_pyt.directives.cpus(4)
   # Generates: test (requires 4 CPUs, no variant name)

**Parameterized CPUs**:

.. code-block:: python

   canary_pyt.directives.parameterize("cpus", [2, 4, 8])
   # Generates: test[cpus=2], test[cpus=4], test[cpus=8]

Edge Cases
----------

**Zero CPUs**:

.. code-block:: python

   canary_pyt.directives.cpus(0)  # Error: Invalid CPU count

**Negative CPUs**:

.. code-block:: python

   canary_pyt.directives.cpus(-1)  # Error: Invalid CPU count

**Very Large CPU Count**:

.. code-block:: python

   canary_pyt.directives.cpus(1000)  # May exceed resource pool capacity

**CPU Override**:

.. code-block:: python

   canary_pyt.directives.cpus(2)
   canary_pyt.directives.cpus(4)  # Overrides to 4 CPUs

Notes
-----

- CPU requirements are meta-parameters, not job name components
- Fixed CPU directives don't create multiple job variants
- Use ``parameterize("cpus", [...])`` to create CPU variants
- CPU allocation is backend-specific (local, HPC, distributed)
- Access CPU IDs at runtime via ``canary.get_instance().cpu_ids``

Runtime Access
--------------

.. code-block:: python

   def main():
       instance = canary.get_instance()
       print(f"CPU IDs: {instance.cpu_ids}")
       print(f"CPU count: {len(instance.cpu_ids)}")

See Also
--------

- :doc:`gpus`: GPU resource directive
- :doc:`nodes`: Node resource directive
- :doc:`parameterize`: Parameterization directive
- :doc:`../resources`: Resource overview
- :doc:`exclusive`: Exclusive resource access
