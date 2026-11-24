.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

The Request Protocol
====================

This page is the specification.  A caller needs only to create, rename and read files.
Everything a caller uses is under the server directory, ``<anchor>/.canary/var/server/``
(the *anchor* is the directory holding ``.canary``):

============================== ======================================================
``server.json``                The server: alive?, version, load (read only)
``inbox/``                     Where requests are submitted (write)
``requests/<id>/``             One request: status, output, result; ``cancel`` (write)
``rejected/``                  Inbox files that could not be taken, with the reason
============================== ======================================================

Everything else there (``server.lock``, ``queue/``, ``accepting/``) is the server's own.
No document a caller reads holds an absolute path of the server's, a pid or a host name.

Submitting
----------

Choose an id, matching ``^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`` and unique in this
workspace.  Write the *envelope* to ``inbox/<id>.json.tmp``, then rename it to
``inbox/<id>.json``; the rename makes it visible whole.  The server ignores ``*.tmp``
files and takes ``inbox/*.json`` oldest first, every fraction of a second.

.. code-block:: json

   {"version": 1, "path": "/canary/run", "request": {"pathspec": ["tests"]},
    "cwd": "tests", "env": {"MY_FLAG": "1"}}

``version``
   ``1`` (optional).
``path``
   The route (required); see :doc:`usage.server.endpoints`.
``request``
   The route's body (default ``{}``).  Unknown fields are rejected.
``cwd``
   The working directory, relative to the anchor, without ``..``, inside the anchor once
   symbolic links are resolved, and existing (default ``"."``).  Paths in the body are
   relative to it, and must lie inside the workspace or a ``server:allowed_roots`` entry.
``env``
   Variables (string to string) set on top of the server's environment for this request.

Any other key is rejected, including ``id``, ``user`` and ``submitted``: the id is the file
name, the user is the file's owner, and every time is the server's clock.

A file whose name is not ``<id>.json`` with a valid id, or whose id is already taken, is
moved to ``rejected/<name>``, with the reason in ``rejected/<name>.reason``; it gets no
``requests/<id>/``.  Every other request ends with exactly one ``requests/<id>/result.json``.

Following a request
-------------------

``requests/<id>/status.json``
   ``state`` is ``queued`` or ``running`` while the request is in progress, then its final
   state, with ``submitted``, ``started`` and ``finished`` times.
``requests/<id>/stdout``, ``stderr``
   A work request's output, appended while it runs; tail it by byte offset.
``requests/<id>/result.json``
   The result.  It does not exist until the request has finished, and is written once,
   whole, after all output.  Wait for this file.

Cancelling
----------

Create ``requests/<id>/cancel``.  A queued request never starts; a running work request is
interrupted (SIGINT, then SIGTERM, then SIGKILL, 10 s apart); a running read is stopped.
Either way the result is ``cancelled``.

The result document
-------------------

.. code-block:: json

   {"version": 1, "id": "r1", "path": "/canary/run", "status_code": 200, "state": "done",
    "data": {"exit_code": 0}, "error": null, "cwd": "tests", "user": "alice",
    "submitted": 1795490933.5, "started": 1795490933.6, "finished": 1795490941.2}

=============  ===============  ===========================================================
``state``      ``status_code``  When
=============  ===============  ===========================================================
``done``       200              It ran.  ``data`` is the endpoint's answer; for work,
                                ``data.exit_code`` is the work's exit code
``rejected``   400, 403, 404,   An invalid envelope or body, a path outside the workspace
               409              and the allowed roots, an unknown route, or a conflict found
                                while running (e.g. a selection that already exists)
``cancelled``  499              The ``cancel`` sentinel
``failed``     500              A server error, the read time limit, the server stopping, or
                                the server dying while the request ran
=============  ===============  ===========================================================

``error`` explains any state but ``done``.  ``started`` is ``null`` for a request that
never started.

The server
----------

``server.json`` exists while a server runs:

.. code-block:: json

   {"version": 1, "state": "running", "started": 1795490900.0, "heartbeat": 1795490933.0,
    "beat": 17, "canary_version": "26.11.18", "running": 1, "queued": 2}

It is rewritten every 2 s.  A caller on another machine judges liveness by ``beat``
changing between two reads a few seconds apart, never by comparing ``heartbeat`` with its
own clock.  Requests dropped while no server runs wait in ``inbox/`` and are taken, in
order, when one starts.

Lanes
-----

Work: ``/canary/run``, ``/canary/hpc/run``, ``/canary/collect``, ``/canary/select``, ``/canary/rebaseline``
   Queued and run **one at a time, in arrival order**, each in its own process.  Each run
   gets the whole machine.  ``hpc run`` holds the lane while its batches wait on the
   scheduler.

Reads: ``/canary/status``, ``/canary/query/*``, ``/canary/schema``
   Run at once, beside the work lane, in up to ``server:read_workers`` threads (extras
   wait, ``queued``).  A read that runs longer than ``server:read_timeout`` seconds is
   stopped and ``failed``.  Reads never write to the workspace.

Retention
---------

When the server starts it removes finished requests, and ``rejected/`` entries, older than
``server:retain_days`` (default 7).

Who can submit
--------------

Anyone who can create files in ``inbox/`` (mode ``0775``: the workspace's owner and
group).  The request runs as the server's user; ``result.json`` records the submitting
file's owner as ``user``.  Grant or restrict access with the directory's permissions.

The HTTP binding (planned)
--------------------------

The routes, bodies and result document are the same over HTTP:

==================  ===================================  ===========================================
Operation           Files (now)                          HTTP (planned)
==================  ===================================  ===========================================
Submit              ``inbox/<id>.json``                  ``POST /canary/<route>``, ``Idempotency-Key:
                                                         <id>``, body = ``request`` → 202 / 200
Progress            ``requests/<id>/status.json``        ``GET /requests/<id>/status``
Result              ``requests/<id>/result.json``        ``GET /requests/<id>`` (404 until finished)
Output              ``requests/<id>/stdout``             ``GET /requests/<id>/stdout`` with ``Range``
Cancel              ``requests/<id>/cancel``             ``POST /requests/<id>/cancel``
Server              ``server.json``                      ``GET /server``
==================  ===================================  ===========================================
