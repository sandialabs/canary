.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Endpoints
=========

Each route takes a JSON body (the envelope's ``request``).  Unknown fields are rejected
with ``400``.  ``/canary/schema`` returns the JSON schema of every body, the envelope and
the result, so a caller can check a request before sending it.

Work
----

These run one at a time (see :doc:`usage.server.requests`).  ``data.exit_code`` is the work's exit code.

``/canary/run``
   Run tests, as ``canary run`` does.  ``pathspec`` (paths, spec ids or a selection tag;
   none: the workspace's tests), ``keyword``, ``owner``, ``parameter``, ``regex``,
   ``only`` (``all``, ``changed``, ``failed``, ``not_pass``, ``not_run``), ``on_options``,
   ``workers``, ``timeout`` (e.g. ``"session=10m"``), ``fail_fast``, ``view`` (e.g.
   ``"mode=symlink"``).  Runs always use the server's workspace; ``only: "failed"`` with no
   ``pathspec`` reruns its failures.  A path in ``pathspec`` defaults to ``only: not_pass``,
   so rerunning tests that passed runs nothing (exit code 7): pass ``only: "all"``.

``/canary/hpc/run``
   Run tests through a scheduler, as ``canary hpc run`` does.  The ``/canary/run`` fields,
   plus ``backend`` (required, e.g. ``"slurm"``), ``batch_spec``, ``batch_workers``,
   ``submit_args``, ``allow_hyperthreading``, ``batch_exact_estimate``.  Requests cannot
   choose an execution prefix: the server's ``CANARY_EXEC_PREFIX``, if set when it
   started, applies to every run.

``/canary/collect``
   Find and generate the test cases under ``roots`` (required) with ``on_options``.
   ``data``: ``{"collected": N}``.  A root that does not exist: ``400``.

``/canary/select``
   Create the selection ``tag`` (required) from all tests, or from ``from_tag``'s, filtered
   by ``from_root`` (paths), ``keyword``, ``owner``, ``parameter``, ``regex``:
   ``{"selected": N}``.  With ``rename_from``, rename that selection to ``tag``; with
   ``delete``, delete ``tag`` (neither takes filters).  An existing ``tag``: ``409``; a
   missing one: ``404``.  Run a selection with ``/canary/run`` and ``pathspec: [tag]``.

``/canary/rebaseline``
   Accept the latest results of ``targets`` (required: job ids or names, or results
   directories), filtered by ``keyword``, as the new baselines: ``{"rebaselined": N}``.

Reads
-----

These answer at once, beside running work.  Jobs come as *job records*, the same as
``canary query jobs`` prints: ``id``, ``name``, ``fullname``, ``file_root`` (the generator's
root), ``file_path`` (the generator's path relative to ``file_root``; the session directory
and the view are laid out by the same relative path), ``exec_path`` (the job's directory,
relative to the session directory), ``exec_dir`` (that directory), ``session``, ``phase``,
``exit_code``, ``status`` (``category``: ``PASS``, ``FAIL``, ``ABORTED``, ``NOTRUN``, ...;
``outcome``; ``reason``), ``timings``, ``duration``, ``started_at``, ``stopped_at`` and
``last_activity``.  The two absolute paths, ``file_root`` and ``exec_dir``, are shown
relative to the workspace, as ``name:path`` under an allowed root, or as ``…/name``
(see ``server:allowed_roots``).

``/canary/status``
   The latest record of every job, or of ``spec_ids``, read from the database alone (HPC
   batch timings and ``last_activity`` are left out; ``/canary/query/jobs`` has them).
   A job that was collected but never ran has category ``NOTRUN`` and an empty ``session``.
   ``spec_ids`` takes ID prefixes or names; omit it for every job (an empty list is
   ``400``).  An unknown job: ``404``; an ambiguous prefix: ``400``.

``/canary/query/sessions``
   Every session's name, oldest first.

``/canary/query/session``
   ``session_id`` (default ``"latest"``): its ``result_count`` and ``outcome_counts``, and
   with ``expand_jobs`` every job record.  Unknown session: ``404``.

``/canary/query/jobs``
   The latest result of every job; with ``session_id``, only those from that session.

``/canary/query/job``
   ``job_id`` (required; a unique prefix or the job's name) in ``session_id`` (default
   ``"latest"``): its job record.  An unknown job, or no result there: ``404``; an
   ambiguous prefix: ``400``.

``/canary/query/failures``
   The jobs of ``session_id`` (default ``"latest"``) whose category is ``FAIL`` or
   ``ABORTED``.

``/canary/query/db``
   One read-only SQL ``SELECT`` (``sql``) on the workspace database:
   ``{"rows": [...], "truncated": bool}``, at most 10 000 rows.  Anything but a single
   ``SELECT``, or bad SQL: ``400``.  A column holding an absolute path is shown as a job
   record's paths are; paths inside JSON columns (``specs.data``) are returned as stored.

``/canary/help``
   Every route the server has registered (core and plugins): ``{"usage": ...,
   "endpoints": {route: {"lane": ..., "summary": ..., "fields": {name: "TYPE, default
   VALUE -- description"}}}}``, generated from the registry, so it always matches the
   server.

``/canary/schema``
   ``{"envelope": ..., "result": ..., "endpoints": {route: {"lane": ..., "request": ...}}}``.
