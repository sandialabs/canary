.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-rebaseline:

Rebaselining tests
==================

It is often necessary to update the baseline values for a test when the outputs change due to modifications in the code. The :ref:`canary rebaseline<canary-rebaseline>` feature allows you to reset the baseline (accepted) values for one or more tests.

.. note::

   For a test to be rebaselined, it must define the baseline instructions.  See :func:`canary_pyt.directives.baseline`.

By default, ``canary rebaseline`` will reset baseline values for all :ref:`stat-diffed` tests.  Eg, running

.. code-block:: console

   canary -C TestResults rebaseline

.. note::

     ``canary rebaseline`` should be run inside of a workspace view by either navigating to it or by ``canary -C PATH``.

For post-processing hooks that derive measurements or artifacts from existing
results, use :doc:`/user/usage.runhook` instead of ``rebaseline``.

``canary rebaseline`` accepts the same filtering arguments as :ref:`canary run<canary-run>`.  Eg, to rebaseline failed tests one can

.. code-block:: console

   canary -C TestResults rebaseline -k fail

To rebaseline specific tests, pass one or more job IDs (or names):

.. code-block:: console

   canary rebaseline ID1 ID2 ID3

Targets may mix job IDs, job names, and results directories.  All targets are
resolved before any baseline is updated, so an unknown ID aborts the command
without changing anything, and a job selected by more than one target is
rebaselined only once.  ``-k`` applies to every target.

Alternatively, change to a test's execution directory and run:

.. code-block:: console

   cd $(canary location ID)
   canary rebaseline .

where ``ID`` is the test's ID.
