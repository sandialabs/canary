.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Batch Layouts
==============

The ``canary_hpc`` extension supports two batch layout strategies: ``flat`` and ``atomic``. These layouts determine how jobs are grouped into batches and how dependencies are handled within and between batches.

Flat Layout
-----------

**Description**: Jobs within a batch do not depend on each other, but batches may depend on other batches.

**Characteristics**:

- No intra-batch job dependencies
- Inter-batch dependencies allowed
- Flexible job grouping
- Efficient resource utilization

**Use Cases**:

- Independent test jobs
- Loosely coupled workloads
- Resource-intensive jobs
- General-purpose batching

**Behavior**:

1. **Job Partitioning**: Jobs grouped by topological level
2. **Node Policy**: Further partitioned by node count (if ``nodes=same``)
3. **Duration Targeting**: Jobs grouped to approximate duration target
4. **Dependency Handling**: Batch dependencies configured globally

**Examples**:

.. code-block:: console

   # Flat layout with default settings
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat ./basic

   # Flat layout with same node count
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,nodes=same ./basic

   # Flat layout with duration targeting
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,duration=30m ./basic

Atomic Layout
-------------

**Description**: Dependency-connected components are kept together; batches do not depend on other batches.

**Characteristics**:

- Intra-batch dependency preservation
- No inter-batch dependencies
- Component-based grouping
- Dependency-aware batching

**Use Cases**:

- Tightly coupled job dependencies
- Workflow-oriented workloads
- Dependency-heavy test suites
- Complex job graphs

**Behavior**:

1. **Component Identification**: Dependency-connected components identified
2. **Component Grouping**: Components kept together in batches
3. **Node Policy**: Requires ``nodes=any`` (cannot use ``nodes=same``)
4. **Count Targeting**: Uses ``count=max`` (no duration targeting)

**Examples**:

.. code-block:: console

   # Atomic layout (requires nodes=any)
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any ./basic

   # Atomic layout with maximum batches
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any,count=max ./basic

Layout Comparison
-----------------

**Flat Layout**:

- ✅ Flexible job grouping
- ✅ Efficient resource utilization
- ✅ Supports duration targeting
- ✅ Works with ``nodes=same`` or ``nodes=any``
- ❌ No intra-batch dependency preservation

**Atomic Layout**:

- ✅ Preserves job dependencies
- ✅ Component-based grouping
- ✅ No inter-batch dependencies
- ❌ Requires ``nodes=any``
- ❌ No duration targeting
- ❌ Uses ``count=max`` only

Layout Selection Guide
----------------------

**Use Flat Layout** when:

- Jobs are independent or loosely coupled
- Resource utilization is a priority
- Duration-based batching is desired
- Node count consistency is important

**Use Atomic Layout** when:

- Jobs have complex dependencies
- Workflow preservation is critical
- Dependency-aware batching is needed
- Component isolation is required

Topological Levels
------------------

Both layouts use topological levels for job partitioning:

**Topological Level**:

- Jobs grouped by dependency level
- Level 0: Jobs with no dependencies
- Level 1: Jobs depending only on level 0
- Level N: Jobs depending on lower levels

**Partitioning**:

- Jobs at same topological level grouped together
- Enables efficient dependency handling
- Preserves execution order constraints

Node Policy Interaction
-----------------------

**nodes=same**:

- All jobs in batch require same node count
- Enables consistent resource allocation
- Works only with flat layout
- Simplifies batch formation

**nodes=any**:

- Jobs with different node counts can be grouped
- Required for atomic layout
- Enables flexible resource utilization
- Supports mixed workloads

Layout Constraints
------------------

**Valid Combinations**:

- ``layout=flat,nodes=same`` ✅
- ``layout=flat,nodes=any`` ✅
- ``layout=atomic,nodes=any`` ✅

**Invalid Combinations**:

- ``layout=atomic,nodes=same`` ❌ (atomic requires nodes=any)
- ``layout=atomic,duration=T`` ❌ (no duration targeting for atomic)

Layout Internals
----------------

Flat Layout Implementation
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Partitioning**:

1. Group jobs by topological level
2. Partition by node count (if ``nodes=same``)
3. Apply duration targeting
4. Create batches

**Batching**:

- Jobs grouped to approximate duration target
- Cheap makespan estimates used
- Batch dependencies configured globally

Atomic Layout Implementation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Component Identification**:

1. Identify dependency-connected components
2. Group components by topological level
3. Preserve component dependencies

**Batching**:

- One component per batch (with ``count=max``)
- No duration targeting
- No inter-batch dependencies

Layout Examples
---------------

Flat Layout Examples
~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Simple flat layout
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat ./basic

   # Flat with same node count
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,nodes=same ./basic

   # Flat with duration targeting
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,duration=30m ./basic

   # Flat with count targeting
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,count=4 ./basic

Atomic Layout Examples
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Simple atomic layout
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any ./basic

   # Atomic with maximum batches
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any,count=max ./basic

   # Atomic with specific count
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any,count=8 ./basic

Layout Debugging
----------------

Debugging layout issues:

.. code-block:: console

   # Check layout behavior with verbose logging
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat --verbose ./basic

   # Test atomic layout
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any --verbose ./basic

   # Compare layout performance
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=flat,duration=30m --verbose ./basic
   python3 -m canary hpc run --backend=slurm --batch-spec=layout=atomic,nodes=any --verbose ./basic

Layout Best Practices
---------------------

1. **Start with Flat**: Use flat layout for initial testing
2. **Layout Selection**: Choose layout based on dependency structure
3. **Node Policy**: Match node policy to workload requirements
4. **Duration Targeting**: Use duration for workload-based batching
5. **Count Targeting**: Use count for specific batch requirements
6. **Validation**: Test layouts with verbose logging
7. **Documentation**: Record layout decisions and rationale
8. **Performance**: Monitor layout performance and adjust as needed