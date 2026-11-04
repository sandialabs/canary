.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-runhook:

Replaying finish hooks
======================

When developing a plugin that implements ``canary_runtest_finish``, it is often
useful to replay that hook on existing results instead of re-running the tests
themselves.  The :ref:`canary runhook<canary-runhook>` command rehydrates jobs
from stored results and invokes the selected hook for each matching job.

The first supported replay target is ``canary_runtest_finish``:

.. code-block:: console

   canary runhook canary_runtest_finish

By default, this uses the configured default run tag and the latest session in
the current workspace.

Filtering with rerun strategies
-------------------------------

``canary runhook canary_runtest_finish`` accepts the same ``--only`` rerun
strategies as :ref:`canary run<canary-run>`:

.. code-block:: console

   canary runhook canary_runtest_finish --only failed
   canary runhook canary_runtest_finish --only not_pass
   canary runhook canary_runtest_finish --only all

This lets you iterate on finish-hook logic only for the subset of jobs that a
normal rerun would select.

Filtering with keywords
-----------------------

Keyword expressions can further narrow the stored jobs whose finish hooks are
replayed:

.. code-block:: console

   canary runhook canary_runtest_finish -k fast
   canary runhook canary_runtest_finish --only failed -k accuracy

This is useful when a plugin is only relevant to one family of jobs.

Choosing a session or explicit targets
--------------------------------------

Use ``--session`` to replay against a specific stored session instead of the
latest one:

.. code-block:: console

   canary runhook canary_runtest_finish --session latest
   canary runhook canary_runtest_finish --session 2026-11-04T11-34

The command also accepts the same result-oriented target forms used by reruns:

.. code-block:: console

   canary runhook canary_runtest_finish JOB_ID
   canary runhook canary_runtest_finish TestResults/fail
   canary runhook canary_runtest_finish my_saved_tag

Notes
-----

* ``runhook`` replays stored jobs; it does not execute test bodies.
* ``canary_runtest_finish`` runs in the job's workspace directory, just as it
  does during normal execution.
* If the hook writes measurements or artifacts back to the job, those changes
  are saved.
* A hook failure does not rewrite the job's original pass/fail outcome, but the
  command returns a nonzero exit code when one or more hook invocations fail.
