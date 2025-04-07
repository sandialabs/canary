.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-batch-basic:

Running tests in a batch scheduler
==================================

Execution in a batch scheduler is accomplished by defining the scheduler and batching scheme on the
command line:

.. code-block:: console

    canary run -b scheduler=[slurm|flux|pbs|shell] -b [count=N|duration=T] PATH

For example, to run the example suite using the ``shell`` scheduler in 4 batches:

.. command-output:: canary run -b scheduler=shell -b count=4 .
    :cwd: /examples
    :setup: rm -rf TestResults
    :returncode: 30
    :nocache:

.. note::

    The ``shell`` scheduler submits batches to the user's shell in a subprocess and is intended for demonstration purposes only.  It should not be used outside of running small examples.
