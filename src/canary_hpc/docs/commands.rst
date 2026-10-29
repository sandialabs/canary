.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Commands
========

``canary_hpc`` adds the ``canary hpc`` command for scheduler-backed execution.
For new usage, prefer these subcommands over the older ``canary run
--hpc-backend=...`` form.

Common Workflow
---------------

The most common sequence is:

.. code-block:: console

   canary hpc info slurm
   canary hpc run --backend=slurm ./tests
   canary hpc log BATCH_ID

That covers backend inspection, batch submission, and post-submit debugging.

canary hpc run
--------------

Use ``canary hpc run`` to collect jobs, form batches, and submit them to the
selected scheduler backend.

.. code-block:: console

   canary hpc run --backend=slurm [options] [paths...]

Common options:

- ``--backend=BACKEND`` selects the scheduler backend.
- ``--batch-spec=SPEC`` controls how jobs are grouped into batches.
- ``--timeout TYPE=T`` configures queue and run timeouts.
- ``--submit-arg=ARG`` passes scheduler-specific submit arguments through to the
  backend.
- ``--workers=N`` limits concurrent batch execution.

Examples:

.. code-block:: console

   canary hpc run --backend=slurm ./tests
   canary hpc run --backend=slurm --batch-spec=duration=30m ./tests
   canary hpc run --backend=slurm --submit-arg="-A myacct,-q debug" ./tests
   canary hpc run --backend=slurm --timeout queue=30m,run=2h ./tests

canary hpc info
---------------

Use ``canary hpc info`` to inspect a backend before you submit work.

.. code-block:: console

   canary hpc info BACKEND

Examples:

.. code-block:: console

   canary hpc info slurm
   canary hpc info pbs
   canary hpc info shell

canary hpc log
--------------

Use ``canary hpc log`` to inspect batch logs after submission.

.. code-block:: console

   canary hpc log [BATCH_ID]

Examples:

.. code-block:: console

   canary hpc log abc123
   canary hpc log

canary hpc exec
---------------

``canary hpc exec`` runs a batch inside its batch workspace. This is usually
called by the scheduler job script, not by a user directly.

.. code-block:: console

   canary hpc exec [options]

Examples:

.. code-block:: console

   canary hpc exec --workspace=/path/to/batches/abc1234 --backend=slurm
   canary hpc exec --workspace=/path/to/batches/abc1234 --workers=4

canary hpc help
---------------

Use ``canary hpc help`` for extra help topics, especially batch specification
help.

.. code-block:: console

   canary hpc help
   canary hpc help --spec

Legacy Forms
------------

The older forms still work:

.. code-block:: console

   canary --hpc-backend=slurm run ./tests
   canary run -b backend=slurm -b spec=duration=30m ./tests

Use them when you need backward compatibility with existing scripts. For new
documentation and new scripts, prefer ``canary hpc run``.

Choosing Between Modern and Legacy Forms
----------------------------------------

Prefer ``canary hpc ...`` when:

- you are writing new commands or documentation
- you want the clearest mapping between command and behavior
- you want the scheduler-backed workflow to be obvious at a glance

Keep the legacy forms when:

- you are maintaining older scripts
- changing the command shape would be disruptive

See Also
--------

- :doc:`overview`: What scheduler-backed execution changes
- :doc:`batch-specification`: Batch grouping rules and examples
- :doc:`scheduler-arguments`: Passing scheduler-specific submit arguments
- :doc:`limitations`: Important operational constraints
