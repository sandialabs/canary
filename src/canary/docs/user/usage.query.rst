.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-query:

Querying workspace data and Canary knowledge
============================================

``canary query`` is the main structured-data interface for inspecting jobs,
sessions, failure summaries, and workspace history. It also provides shortcut
flags for querying installed capabilities and skills.

Use this page for common workflows. For the full command-line surface area, see
:ref:`canary query <canary-query>`.

What ``canary query`` is for
----------------------------

Use ``canary query`` when you want machine-readable output instead of the
human-oriented summaries from commands like ``canary status`` or ``canary log``.
Typical uses include:

- inspecting one job's structured status, environment, measurements, or resources
- expanding a session into per-job result rows
- comparing sessions to spot regressions
- grouping failures by signature or exception
- retrieving capability and skill data through query shortcuts

Inspect a single job
--------------------

Start with ``canary query job`` when you already know the job ID:

.. code-block:: console

   canary query job JOB_ID
   canary query job JOB_ID status.outcome
   canary query job JOB_ID measurements
   canary query job JOB_ID env
   canary query job JOB_ID env.CUDA_VISIBLE_DEVICES

Useful job-focused options include:

- ``--all-runs`` to show historical runs of the same job across sessions
- ``--blockers`` to explain which dependency failures prevented the job from running
- ``--missing-inputs`` to summarize staged-input problems
- ``--list`` to discover which child fields are available at the selected path

Shortcut form:

.. code-block:: console

   canary query -j JOB_ID status.outcome

Inspect a session
-----------------

Use ``canary query session`` to inspect one session's metadata or to expand it
into job rows:

.. code-block:: console

   canary query session latest
   canary query session latest --expand-jobs
   canary query session latest --expand-jobs --where status.outcome==FAILED
   canary query session latest --digest
   canary query session latest --watch

This is the best entry point when you want to answer questions like:

- Which jobs failed in the latest session?
- Which jobs took the longest?
- Which jobs are still running?
- Which jobs are missing staged inputs?

Shortcut form:

.. code-block:: console

   canary query -s latest
   canary query -s latest measurements

Query jobs across sessions
--------------------------

Use ``canary query jobs`` when you want the latest result per job across the
workspace, or when you want to restrict the query to one session but still work
with a flat job list:

.. code-block:: console

   canary query jobs
   canary query jobs --where status.category==FAIL
   canary query jobs --where timings.running>60
   canary query jobs --session latest --digest
   canary query jobs --with logs:40

This is useful for large triage loops where you want to filter, summarize, or
export structured rows without repeatedly invoking ``canary log``.

Compare sessions and group failures
-----------------------------------

Two high-value workflows are regression comparison and grouped failure analysis:

.. code-block:: console

   canary query compare BASE_SESSION NEW_SESSION
   canary query compare BASE_SESSION NEW_SESSION --digest
   canary query compare BASE_SESSION NEW_SESSION --signatures

   canary query failures --session latest
   canary query failures --group-by signature
   canary query failures --group-by exception --terse

Use ``compare`` when you want to know what changed between two runs. Use
``failures`` when you want to collapse many failing jobs into a smaller number
of likely root causes.

Capabilities and skill shortcuts
--------------------------------

``canary query`` also exposes two shortcuts into the knowledge data provided by
``canary learn``:

.. code-block:: console

   canary query -c .
   canary query -c core.overview
   canary query -c hooks --list

   canary query --skills .
   canary query --skills core.canary-orientation
   canary query --skills --list

These are convenient when you are already using ``canary query`` as the main
inspection command. For a fuller explanation of capabilities versus skills, see
:doc:`/user/usage.learn`.

Database-oriented inspection
----------------------------

Use ``canary query db`` for lightweight database introspection:

.. code-block:: console

   canary query db stats
   canary query db schema
   canary query db "SELECT spec_name, status_outcome FROM results LIMIT 10"

This is mainly for diagnostics, debugging, or ad hoc investigation of workspace
state when higher-level commands are not specific enough.

When to use query vs status/log
-------------------------------

- Use ``canary status`` when you want a quick human-readable summary.
- Use ``canary log`` when you want stdout, stderr, or other files from a job directory.
- Use ``canary query`` when you want structured fields, filtering, scripting, or cross-session comparison.

See also
--------

- :doc:`/user/usage.debugging` for a triage-oriented debugging workflow
- :doc:`/user/usage.learn` for installed capabilities and skills
- :ref:`canary query <canary-query>` for the generated command reference
