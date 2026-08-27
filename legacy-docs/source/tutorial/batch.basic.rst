.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-batch-basic:

Running tests in a batch scheduler
==================================

Execution in a batch scheduler is accomplished by defining the scheduling backend and batching
scheme on the command line:

.. code-block:: console

    canary run -b backend=(slurm|flux|pbs|shell) -b spec=[(count:(N|max|auto)|duration:T)][,layout:(flat|atomic)][,nodes:(any|same)] PATH

For example, to run the example suite using the ``shell`` backend in 4 batches:

.. doc-run::
   :before_script: [copy-examples]
   :script: ['canary run -b backend=shell -b spec=count:4 .']
   :cwd: /examples
   :anyreturncode:

.. note::

    The ``shell`` backend submits batches to the user's shell in a subprocess and is intended for demonstration purposes only.  It should not be used outside of running small examples.
