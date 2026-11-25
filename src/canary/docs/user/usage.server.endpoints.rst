.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Endpoints
=========

Each route takes a JSON body (the envelope's ``request``).  Unknown fields are rejected
with ``400``.  A route may also carry values: ``/canary/query/job/{job_id}`` takes
``job_id`` from the route (giving it in the body too is ``400``), and a route ending
``{path:path}`` takes the rest, keys separated by ``/``, as a path into what it returns.  ``/canary/schema`` returns the JSON schema of every body, the envelope and
the result, so a caller can check a request before sending it.

Work
----

These run one at a time (see :doc:`usage.server.requests`).  ``data.exit_code`` is the work's exit code
(``/canary/help`` lists them as ``exit_codes``).  If canary crashed while running a
session, ``/canary/run`` and ``/canary/hpc/run`` add ``data.session_error`` (the
exception, e.g. ``"RuntimeError: ..."``; also the session's ``error``): its jobs show as
cancelled or unfinished, through no fault of theirs.  If jobs passed but their
``canary_runtest_finish`` hook failed (``PASS_WITH_ERRORS``), they add
``data.pass_with_errors``, their number: they pass, so the exit code omits them.

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
``outcome``; ``reason``), ``timings``, ``duration``, ``started_at``, ``stopped_at``,
``last_activity`` and ``measurements`` (name to value, as ``add_measurement`` recorded
them).  The two absolute paths, ``file_root`` and ``exec_dir``, are shown
relative to the workspace, as ``name:path`` under an allowed root, or as ``…/name``
(see ``server:allowed_roots``).

``/canary/status``
   The latest record of every job, or of ``spec_ids``, read from the database alone (HPC
   batch timings and ``last_activity`` are left out; ``/canary/query/jobs`` has them).
   A job that was collected but never ran has category ``NOTRUN`` and an empty ``session``.
   ``spec_ids`` takes ID prefixes or names; omit it for every job (an empty list is
   ``400``).  An unknown job: ``404``; an ambiguous prefix: ``400``.

``/canary/query/sessions``
   Every session's summary, oldest first, as ``canary query sessions`` prints it: ``name``,
   ``started_on``, ``finished_on``, ``returncode``, ``argv``, ``job_count``, ``outcomes``.

``/canary/query/session/{session_id}``, ``/canary/query/session/{session_id}/{path:path}``
   The session (``latest`` for the newest): ``session_id``, ``result_count``,
   ``outcome_counts``, the fields of its ``session.lock`` (``started_on``,
   ``finished_on``, ``returncode``, ``argv``, ``config``, ...) and ``jobs``, every job
   record.  With a path, that part of it (``.../session/latest/outcome_counts``,
   ``.../session/latest/jobs/0/measurements``).  Unknown session: ``404``.

``/canary/query/jobs``
   The latest result of every job; with ``session_id``, only those from that session.

``/canary/query/job/{job_id}``, ``/canary/query/job/{job_id}/{path:path}``
   One run of the job ``job_id`` (a unique prefix or the job's name): its latest, or its
   run in ``session_id`` (body; a name or ``latest``).  Its job record, plus from its
   ``testcase.lock`` ``spec`` (parameters, keywords, command, ...), ``dependencies``,
   ``variables``, ``allocation`` and ``rparameters``.  With a path, that part of it:
   ``.../job/ID/measurements/loss``, ``.../job/ID/spec/parameters``; ``.../job/ID/env`` is
   the run's environment (``env.json``), there only when asked for.  A key is taken whole,
   so one holding a dot needs no quoting; a list takes an index.  An unknown job, no
   result there, or a missing key (the error lists the keys there): ``404``; an ambiguous
   prefix: ``400``.  Paths inside ``spec``, ``variables`` and ``env`` are returned as
   stored.

``/canary/query/job/{job_id}/log``
   What a run of the job printed, as ``canary log`` shows it: ``{"path", "text",
   "lines"}``, the file (relative to the workspace), its text and its number of lines.
   ``tail`` keeps only the last lines; ``stream`` is ``stdout`` (default; ``canary-out.txt``,
   which holds stderr too unless the job split it off) or ``stderr``; ``session_id`` as
   for the job.  Nothing written to the stream: ``404``.

``/canary/location/{job_id}``
   Where the job's files are, as ``canary location`` finds them: ``exec_dir`` (its entry
   in the view, else its session directory; ``-x``), ``log`` (``-l``), ``input`` (the file
   that defines it; ``-i``) and ``source_dir`` (``-s``), each relative to the workspace
   (or ``name:path`` under an allowed root), so they open on any machine that mounts it.
   A job that never ran has no ``exec_dir`` or ``log`` (``null``).

``/canary/query/failures``
   The jobs of ``session_id`` (default ``"latest"``) that need attention: category
   ``FAIL`` or ``ABORTED``, and outcome ``PASS_WITH_ERRORS`` (passed, but a finish hook
   failed).  With ``log_tail`` (a number of lines), each record also has ``log_tail``: the end of
   what the job printed (``null`` if nothing), as ``/canary/query/job/{job_id}/log`` gives
   it with ``tail``.

``/canary/query/db``
   One read-only SQL ``SELECT`` (``sql``) on the workspace database:
   ``{"rows": [...], "truncated": bool}``, at most 10 000 rows.  ``params`` holds the
   values of the statement's ``?`` parameters, in order.  With ``parse_json``, JSON text
   columns (``measurements``, ``timekeeper``, ``specs.data``) come as objects, a
   ``measurements`` column as in job records.  Anything but a single ``SELECT``, or bad
   SQL: ``400`` (``PRAGMA`` too: use ``/canary/query/db/schema``).  A column holding an absolute path is shown as a job
   record's paths are; paths inside JSON columns (``specs.data``) are returned as stored.

``/canary/query/db/schema``, ``/canary/query/db/schema/{path:path}``
   The database's tables, as ``{table: {"columns": [{"name", "type", "notnull", "pk"}],
   "sql": "CREATE TABLE ..."}}``; with a path, part of it
   (``.../schema/results/columns``).

``/canary/query/db/stats``
   ``canary query db stats``: ``spec_count``, ``result_count``, ``session_count``,
   ``latest_session`` and ``outcomes`` (the latest result of each spec, by outcome).

``/canary/learn/capabilities``, ``/canary/learn/skills``
   The installed capability and skill data, as ``canary learn capabilities TOPIC`` and
   ``canary learn skills TOPIC`` print it (``canary query -c`` / ``--skills``): ``topic``
   (default ``"."``, everything) and ``list_keys`` (the keys below ``topic`` instead of
   its data, as ``--list``).  An unknown topic: ``404``.  Callers without canary installed
   read the reference the skills point to here.

``/canary/help``
   Every route the server has registered (core and plugins): ``{"usage": ...,
   "endpoints": {route: {"lane": ..., "summary": ..., "fields": {name: "TYPE, default
   VALUE -- description"}}}}``, generated from the registry, so it always matches the
   server.

``/canary/schema``
   ``{"envelope": ..., "result": ..., "endpoints": {route: {"lane": ..., "request": ...}}}``.
