.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

gpus
====

.. currentmodule:: canary_pyt.directives

.. autofunction:: gpus

Purpose
-------

Set the fixed GPU resource requirement for a job. This directive specifies the number of GPUs required to execute the job.

Parameters
----------

:param arg: Number of GPUs (int)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Sets a fixed GPU resource meta-parameter
- Does NOT create named job variants (unlike ``parameterize("gpus", ...)``)
- GPU requirement is enforced by the resource pool
- Accessible via ``instance.gpu_ids`` at runtime

When
----

- **Affects**: Generation phase
- **Runtime**: GPU allocation during execution

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.gpus(2, when="-o gpu_tests")

Examples
--------

**Fixed GPU Requirement**:

.. code-block:: python

   canary_pyt.directives.gpus(1)  # Requires 1 GPU

**Multiple GPU Requirement**:

.. code-block:: python

   canary_pyt.directives.gpus(4)  # Requires 4 GPUs

**Conditional GPU Requirement**:

.. code-block:: python

   canary_pyt.directives.gpus(2, when="keywords=gpu")

Comparison with parameterize
----------------------------

**Fixed GPUs (this directive)**:

.. code-block:: python

   canary_pyt.directives.gpus(2)
   # Generates: test (requires 2 GPUs, no variant name)

**Parameterized GPUs**:

.. code-block:: python

   canary_pyt.directives.parameterize("gpus", [1, 2, 4])
   # Generates: test[gpus=1], test[gpus=2], test[gpus=4]

Edge Cases
----------

**Zero GPUs**:

.. code-block:: python

   canary_pyt.directives.gpus(0)  # Valid: No GPU requirement

**Negative GPUs**:

.. code-block:: python

   canary_pyt.directives.gpus(-1)  # Error: Invalid GPU count

**GPU Override**:

.. code-block:: python

   canary_pyt.directives.gpus(1)
   canary_pyt.directives.gpus(2)  # Overrides to 2 GPUs

**No GPU Available**:

.. code-block:: python

   canary_pyt.directives.gpus(1)  # Error if no GPUs in resource pool

Notes
-----

- GPU requirements are meta-parameters, not job name components
- Fixed GPU directives don't create multiple job variants
- Use ``parameterize("gpus", [...])`` to create GPU variants
- GPU allocation is backend-specific (local, HPC, distributed)
- Access GPU IDs at runtime via ``canary.get_instance().gpu_ids``
- GPU support requires appropriate hardware and drivers

Runtime Access
--------------

.. code-block:: python

   def main():
       instance = canary.get_instance()
       if instance.gpu_ids:
           print(f"GPU IDs: {instance.gpu_ids}")
           print(f"GPU count: {len(instance.gpu_ids)}")
       else:
           print("No GPUs allocated")

See Also
--------

- :doc:`cpus`: CPU resource directive
- :doc:`nodes`: Node resource directive
- :doc:`parameterize`: Parameterization directive
- :doc:`../resources`: Resource overview
- :doc:`exclusive`: Exclusive resource access
