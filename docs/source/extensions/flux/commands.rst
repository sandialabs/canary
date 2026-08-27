.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Commands
========

The ``canary_flux`` extension provides commands for direct Flux execution and management. These commands enable users to submit, monitor, and debug Flux executions.

Flux Commands
-------------

The ``canary flux`` command provides subcommands for Flux operations:

.. code-block:: console

   python3 -m canary flux [-h] [subcommand] ...

Subcommands
~~~~~~~~~~~

flux run
^^^^^^^^

**Purpose**: Run Canary jobs individually inside a Flux allocation

**Usage**:

.. code-block:: console

   python3 -m canary flux run [options] [paths...]

**Description**:

The ``flux run`` command collects jobs and runs each one individually as a Flux JobSpecV1 within an active Flux allocation. It replaces Canary's local execution with direct Flux submission, providing fine-grained control over job execution.

**Options**:

- ``--nodes N``: Minimum number of nodes to request for the Flux allocation [default: auto]
- ``--submit-arg ARG``: Additional argument passed to inner Flux/hpc_connect job submission; may be repeated
- ``--alloc-arg ARG``: Additional argument passed to Flux/hpc_connect allocation request; may be repeated
- ``--workers N``: Maximum number of concurrent jobs to submit to the flux allocation [default: None]
- ``--timeout TYPE=T``: Timeout configuration (queue or allocation)
- Standard Canary test selection and execution options

**Timeout Types**:

- ``type=queue``: Maximum time to wait for the Flux allocation or submitted Flux job to start before treating it as timed out
- ``type=allocation``: Walltime requested for the outer Flux allocation

**Examples**:

.. code-block:: console

   # Run with Flux allocation (auto node count)
   python3 -m canary flux run ./basic

   # Run with specific node count
   python3 -m canary flux run --nodes 4 ./basic

   # Run with allocation arguments
   python3 -m canary flux run --alloc-arg="--time-limit=60" ./basic

   # Run with submission arguments
   python3 -m canary flux run --submit-arg="--queue=debug" ./basic

   # Run with multiple submission arguments
   python3 -m canary flux run --submit-arg="--queue=debug" --submit-arg="--account=myacct" ./basic

   # Run with timeout configuration
   python3 -m canary flux run --timeout queue=30m,allocation=2h ./basic

   # Run with worker limit
   python3 -m canary flux run --workers 8 ./basic

flux exec
^^^^^^^^^

**Purpose**: Execute one Canary job inside a Flux allocation

**Usage**:

.. code-block:: console

   python3 -m canary flux exec [options]

**Description**:

The ``flux exec`` command executes a single Canary job inside the active Flux allocation. This command is typically called by the Flux scheduler when a job starts, not directly by users. It runs the specified job and writes results to the workspace database FSQueue.

**Options**:

- ``--session SESSION``: Run the job in this session (required)
- ``SPEC``: Run this spec ID (required)

**Examples**:

.. code-block:: console

   # Execute specific job in session (called by Flux scheduler)
   python3 -m canary flux exec --session my_session abc123def456

Command Integration
-------------------

The Flux commands integrate with Canary through several mechanisms:

**Subcommand Registration**:

The ``canary_addcommand`` hook registers the ``flux`` command with ``run`` and ``exec`` subcommands.

**Resource Pool Management**:

The ``canary_resource_pool_fill`` hook creates a Flux resource pool from the `hpc_connect` backend when ``flux_direct_run`` is enabled.

**Execution Workflow**:

The ``canary_runtests`` hook implements the Flux allocation and execution workflow when ``flux_direct_run`` is enabled.

**Environment Capture**:

The ``canary_runtest_finish`` hook captures the full environment to ``env.json`` for debugging purposes.

Command Examples
----------------

Basic Flux Execution
~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Run tests through Flux
   python3 -m canary flux run ./basic

   # Run with specific backend (if multiple Flux backends configured)
   python3 -m canary flux run --flux-backend=myflux ./basic

Resource Management
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Run with auto-detected node count
   python3 -m canary flux run ./basic

   # Run with explicit node count
   python3 -m canary flux run --nodes 2 ./basic

   # Run with backend that has 8 nodes
   python3 -m canary flux run ./basic

Timeout Configuration
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Run with queue timeout
   python3 -m canary flux run --timeout queue=30m ./basic

   # Run with allocation walltime
   python3 -m canary flux run --timeout allocation=2h ./basic

   # Run with both timeouts
   python3 -m canary flux run --timeout queue=30m,allocation=2h ./basic

Concurrency Control
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Run with unlimited concurrency (default)
   python3 -m canary flux run ./basic

   # Run with worker limit
   python3 -m canary flux run --workers 4 ./basic

   # Run with higher concurrency
   python3 -m canary flux run --workers 16 ./basic

Scheduler Arguments
~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   # Run with allocation arguments
   python3 -m canary flux run --alloc-arg="--time-limit=60" ./basic

   # Run with submission arguments
   python3 -m canary flux run --submit-arg="--queue=debug" ./basic

   # Run with multiple arguments
   python3 -m canary flux run --alloc-arg="--exclusive" --submit-arg="--priority=high" ./basic

Test Selection
~~~~~~~~~~~~~~

.. code-block:: console

   # Run specific tests
   python3 -m canary flux run ./tests/test_math.py

   # Run with test selection
   python3 -m canary flux run -k "test_add" ./basic

   # Run with parameter selection
   python3 -m canary flux run -p "cpus=8" ./basic

   # Run with owner filter
   python3 -m canary flux run --owner "john" ./basic

Command Best Practices
----------------------

1. **Backend Specification**: Use auto-detected backend or specify explicitly with ``--flux-backend``
2. **Resource Management**: Configure resources in `hpc_connect` Flux backend, not Canary
3. **Timeout Configuration**: Set appropriate queue and allocation timeouts
4. **Concurrency Control**: Use ``--workers`` to limit concurrent job submission
5. **Error Handling**: Monitor job status and Flux logs
6. **Debugging**: Use workspace inspection and ``env.json`` files
7. **Documentation**: Record command usage and configurations
8. **Node Count**: Start with auto-detection, then optimize based on workload

Command Selection Guide
-----------------------

**Use ``canary flux run``** when:

- You need direct Flux Framework execution
- You want fine-grained control over individual jobs
- You're working with Flux allocations directly
- You need detailed timing metrics for Flux overhead
- You prefer individual job submission over batching

**Use ``canary hpc run --backend=flux``** when:

- You need batching capabilities
- You want to use Flux as one of multiple backends
- You need large-scale job organization
- You're migrating from other HPC schedulers
- You need batch-level status aggregation

Both approaches use Flux, but ``canary flux`` provides direct integration while ``canary hpc`` provides batching infrastructure.
