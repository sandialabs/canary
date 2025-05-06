.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-rebaseline:

Rebaselining tests
==================

It is often necessary to update the baseline values for a test when the outputs change due to modifications in the code. The :ref:`canary rebaseline<canary-rebaseline>` feature allows you to reset the baseline (accepted) values for one or more tests.

.. note::

   For a test to be rebaselined, it must define the baseline instructions.  See :func:`canary.directives.baseline`.

By default, ``canary rebaseline`` will reset baseline values for all :ref:`stat-diffed` tests.  Eg, running

.. code-block:: console

   canary -C TestResults rebaseline

.. note::

    ``canary rebaseline`` should be run inside of a test session by either navigating to the session's directory or by ``canary -C PATH``.

``canary rebaseline`` accepts the same filtering arguments as :ref:`canary run<canary-run>`.  Eg, to rebaseline failed tests one can

.. code-block:: console

   canary -C TestResults rebaseline -k fail

To rebaseline a single test, change to that tests execution directory and run:

.. code-block:: console

   cd $(canary -C TestResults location /ID)
   canary rebaseline .

where ``ID`` is the test's ID.
