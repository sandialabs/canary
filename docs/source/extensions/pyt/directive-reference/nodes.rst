.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

nodes
=====

.. currentmodule:: canary_pyt.directives

.. autofunction:: nodes

Purpose
-------

Set the fixed node resource requirement for a job. This directive specifies the number of nodes required to execute the job.

Parameters
----------

:param arg: Number of nodes (int)
:param when: Optional conditional activation (WhenType)

Effect on Generated Jobs
------------------------

- Sets a fixed node resource meta-parameter
- Does NOT create named job variants (unlike ``parameterize("nodes", ...)``)
- Node requirement is enforced by the resource pool
- Primarily used in HPC/distributed environments

When
----

- **Affects**: Generation phase
- **Runtime**: Node allocation during execution

Conditional Activation
----------------------

Supports ``when`` parameter for conditional activation:

.. code-block:: python

   canary_pyt.directives.nodes(4, when="-o distributed")

Examples
--------

**Single Node Requirement**:

.. code-block:: python

   canary_pyt.directives.nodes(1)  # Requires 1 node

**Multiple Node Requirement**:

.. code-block:: python

   canary_pyt.directives.nodes(4)  # Requires 4 nodes

**Conditional Node Requirement**:

.. code-block:: python

   canary_pyt.directives.nodes(2, when="keywords=distributed")

Comparison with parameterize
----------------------------

**Fixed Nodes (this directive)**:

.. code-block:: python

   canary_pyt.directives.nodes(2)
   # Generates: test (requires 2 nodes, no variant name)

**Parameterized Nodes**:

.. code-block:: python

   canary_pyt.directives.parameterize("nodes", [1, 2, 4])
   # Generates: test[nodes=1], test[nodes=2], test[nodes=4]

Edge Cases
----------

**Zero Nodes**:

.. code-block:: python

   canary_pyt.directives.nodes(0)  # Error: Invalid node count

**Negative Nodes**:

.. code-block:: python

   canary_pyt.directives.nodes(-1)  # Error: Invalid node count

**Node Override**:

.. code-block:: python

   canary_pyt.directives.nodes(1)
   canary_pyt.directives.nodes(2)  # Overrides to 2 nodes

**Single Node Default**:

.. code-block:: python

   # No nodes directive specified
   # Default: 1 node (backend-specific)

Notes
-----

- Node requirements are meta-parameters, not job name components
- Fixed node directives don't create multiple job variants
- Use ``parameterize("nodes", [...])`` to create node variants
- Node allocation is backend-specific (primarily HPC/distributed)
- In local execution, nodes typically map to a single machine
- Node requirements may affect job scheduling in resource pools
- Combines with CPU/GPU requirements for total resource allocation

Resource Interaction
--------------------

Node, CPU, and GPU requirements interact:

.. code-block:: python

   canary_pyt.directives.nodes(2)    # 2 nodes
   canary_pyt.directives.cpus(8)     # 8 CPUs total (4 per node if distributed)
   canary_pyt.directives.gpus(2)     # 2 GPUs total

Total resource requirement: 2 nodes, 8 CPUs, 2 GPUs

See Also
--------

- :doc:`cpus`: CPU resource directive
- :doc:`gpus`: GPU resource directive
- :doc:`parameterize`: Parameterization directive
- :doc:`../resources`: Resource overview
- :doc:`exclusive`: Exclusive resource access
