.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Commands
========

``canary_flux`` adds the ``canary flux`` command for direct execution inside a
Flux allocation.

Common Workflow
---------------

The usual workflow is to request an allocation and run a test suite directly in
it:

.. code-block:: console

   canary flux run ./tests

Then add allocation, timeout, or worker controls as needed.

canary flux run
---------------

Use ``canary flux run`` to collect jobs, request a Flux allocation, and submit
each selected Canary job inside that allocation.

.. code-block:: console

   canary flux run [options] [paths...]

Common options:

- ``--nodes N`` requests a larger allocation.
- ``--alloc-arg ARG`` passes arguments to the outer allocation request.
- ``--submit-arg ARG`` passes arguments to inner Flux job submission.
- ``--workers N`` limits how many jobs are submitted concurrently.
- ``--timeout TYPE=T`` configures queue and allocation timeouts.

Examples:

.. code-block:: console

   canary flux run ./tests
   canary flux run --nodes 4 ./tests
   canary flux run --alloc-arg="--time-limit=60" ./tests
   canary flux run --submit-arg="--queue=debug" ./tests
   canary flux run --timeout queue=30m,allocation=2h ./tests
   canary flux run --workers 8 ./tests

canary flux exec
----------------

``canary flux exec`` runs one Canary job inside the active Flux allocation.
This is normally called by Flux rather than by a user directly.

.. code-block:: console

   canary flux exec [options]

Example:

.. code-block:: console

   canary flux exec --session my_session abc123def456

Choosing Between canary flux and canary hpc
-------------------------------------------

Prefer ``canary flux run`` when:

- you want direct Flux execution
- each job should be submitted individually
- you care about per-job Flux timing and lifecycle details

Prefer ``canary hpc run --backend=flux`` when:

- you want batching
- you are using the same operational model across multiple scheduler backends
- batch-level status and packing policy matter more than per-job directness

Debugging-Oriented Examples
---------------------------

.. code-block:: console

   canary flux run --workers 4 ./tests
   canary flux run --timeout queue=30m ./tests
   canary flux run -k "smoke" ./tests
   canary flux run -p "cpus=8" ./tests

See Also
--------

- :doc:`overview`: Direct Flux execution model
- :doc:`resource-management`: Resource pool and assignment behavior
- :doc:`timeouts`: Timeout behavior in Flux mode
- :doc:`limitations`: Important constraints of direct Flux execution
