.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-batch-args:

Sending options to the batch scheduler
======================================

Options passed to ``canary`` with ``-b option=OPTION`` are forwarded directly to the scheduler. For
example,

.. code-block:: console

    canary run -b scheduler=slurm -b option=--account=ABC123 PATH

will pass ``--account=ABC123`` to ``sbatch``.

Comma splitting
---------------

If ``OPTION`` contains commas, it is split into multiple scheduler options at the commas. For
example,

.. code-block:: console

    canary run -b scheduler=slurm -b option=--account=ABC123,--queue=debug PATH

will pass ``--account=ABC123`` and ``--queue=debug`` to ``sbatch``.

You can also pass multiple ``option=...`` entries explicitly:

.. code-block:: console

    canary run -b scheduler=slurm -b option=--account=ABC123 -b option=--queue=debug PATH

Quoting options that contain commas
-----------------------------------

If the *scheduler option itself* contains commas, quote it so the shell treats it as a single
argument. For example:

.. code-block:: console

    canary run -b scheduler=slurm -b option=--queue='debug,short' PATH

Without quotes, the comma would be interpreted as an option separator and would be split into
multiple scheduler options.
