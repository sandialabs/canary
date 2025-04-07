.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-batch-args:

Sending options to the batch scheduler
======================================

Options passed to ``canary`` by the ``-b option=OPTION`` flag are forwarded directly to the scheduler.  For example,

.. code-block:: console

    canary run -b scheduler=slurm -b option=--account=ABC123 PATH

will pass ``--account=ABC123`` to ``sbatch``.

If ``OPTION`` contains commas, it is split into multiple options at the commas.  E.g.,

.. code-block:: console

    canary run -b scheduler=slurm -b option=--account=ABC123,--queue=debug PATH

will pass ``--account=ABC123`` and ``--queue=debug`` to ``sbatch``.

``OPTION``\ s can be passed separately, e.g.:

.. code-block:: console

    canary run -b scheduler=slurm -b option=--account=ABC123 -b option=--queue=debug PATH

will also pass ``--account=ABC123`` and ``--queue=debug`` to ``sbatch``.
