.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Resources
=========

Resource directives specify the computational resources required by jobs. Resources are allocated from Canary's resource pool and affect job scheduling and execution.

Resource Directives
-------------------

### Fixed Resources

Fixed resource directives set meta-parameters that do not create named job variants:

**cpus(N)**
   Set fixed CPU requirement without adding to job name.

.. code-block:: python

   canary_pyt.directives.cpus(4)  # Requires 4 CPUs

**gpus(N)**
   Set fixed GPU requirement without adding to job name.

.. code-block:: python

   canary_pyt.directives.gpus(2)  # Requires 2 GPUs

**nodes(N)**
   Set fixed node requirement without adding to job name.

.. code-block:: python

   canary_pyt.directives.nodes(2)  # Requires 2 nodes

### Parameterized Resources

Parameterized resource directives create named job variants:

**parameterize("cpus", [...])**
   Create CPU variants with different CPU counts.

.. code-block:: python

   canary_pyt.directives.parameterize("cpus", [2, 4, 8])
   # Generates: test[cpus=2], test[cpus=4], test[cpus=8]

**parameterize("gpus", [...])**
   Create GPU variants with different GPU counts.

.. code-block:: python

   canary_pyt.directives.parameterize("gpus", [1, 2, 4])
   # Generates: test[gpus=1], test[gpus=2], test[gpus=4]

**parameterize("nodes", [...])**
   Create node variants with different node counts.

.. code-block:: python

   canary_pyt.directives.parameterize("nodes", [1, 2, 4])
   # Generates: test[nodes=1], test[nodes=2], test[nodes=4]

Fixed vs Parameterized
----------------------

**Fixed Resources**:

.. code-block:: python

   canary_pyt.directives.cpus(4)
   # Job: test (requires 4 CPUs, no variant name)

**Parameterized Resources**:

.. code-block:: python

   canary_pyt.directives.parameterize("cpus", [2, 4, 8])
   # Jobs: test[cpus=2], test[cpus=4], test[cpus=8]

Meta-Parameters
---------------

Fixed resource directives are **meta-parameters**:

- Do not affect job naming
- Set resource requirements for all jobs
- Enforced by the resource pool
- Accessible at runtime via instance attributes

Resource IDs
------------

Resource IDs are exposed at runtime:

.. code-block:: python

   def main():
       instance = canary.get_instance()
       print(f"CPU IDs: {instance.cpu_ids}")
       print(f"GPU IDs: {instance.gpu_ids}")
       print(f"Node count: {len(instance.cpu_ids) // cpus_per_node}")

Exclusive Resources
-------------------

**exclusive**
   Mark job as requiring exclusive resource access.

.. code-block:: python

   canary_pyt.directives.exclusive()
   canary_pyt.directives.cpus(8)

Exclusive jobs:

- Have dedicated resources
- Do not share resources with other jobs
- Use for performance-sensitive tests
- May reduce resource pool utilization

Resource Pool Relationship
--------------------------

Resources are allocated from Canary's resource pool:

1. Job specifies resource requirements
2. Canary checks resource pool capacity
3. Job is scheduled when resources are available
4. Resources are allocated during execution
5. Resources are released after completion

Combined Resources
------------------

Resources combine to form total requirements:

.. code-block:: python

   canary_pyt.directives.nodes(2)    # 2 nodes
   canary_pyt.directives.cpus(8)     # 8 CPUs total
   canary_pyt.directives.gpus(2)     # 2 GPUs total

Total: 2 nodes, 8 CPUs, 2 GPUs

Resource Limitations
--------------------

**Pool Capacity**:
   Jobs wait if resources are not available.

**Backend-Specific**:
   Resource allocation depends on execution backend.

**Over-subscription**:
   Requesting more resources than available causes scheduling delays.

Best Practices
--------------

1. **Fixed Resources for Consistent Requirements**:

   .. code-block:: python

      canary_pyt.directives.cpus(4)
      canary_pyt.directives.gpus(1)

2. **Parameterized Resources for Scaling Tests**:

   .. code-block:: python

      canary_pyt.directives.parameterize("cpus", [2, 4, 8])

3. **Exclusive for Performance Tests**:

   .. code-block:: python

      canary_pyt.directives.exclusive()
      canary_pyt.directives.cpus(8)

4. **Conditional Resources**:

   .. code-block:: python

      canary_pyt.directives.cpus(4, when="-o high_performance")

Examples
--------

**Fixed CPU and GPU**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.cpus(4)
   canary_pyt.directives.gpus(1)
   canary_pyt.directives.timeout(60)

**Parameterized CPU**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.parameterize("cpus", [2, 4, 8])
   canary_pyt.directives.gpus(1)

**Exclusive Resources**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.exclusive()
   canary_pyt.directives.cpus(8)
   canary_pyt.directives.gpus(2)

**Conditional Resources**:

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.cpus(2)
   canary_pyt.directives.cpus(4, when="-o extended")

See Also
--------

- :doc:`directive-reference/cpus`: CPU resource directive
- :doc:`directive-reference/gpus`: GPU resource directive
- :doc:`directive-reference/nodes`: Node resource directive
- :doc:`directive-reference/exclusive`: Exclusive resource directive
- :doc:`directive-reference/parameterize`: Parameterization directive
- :doc:`execution-model`: Execution model details
