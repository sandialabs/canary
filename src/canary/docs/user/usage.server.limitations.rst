.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Limitations
===========

* **One work request at a time.**  Work requests do not share the resource pool, so they
  run in sequence.  This costs little for local runs (each fills the machine), but
  ``/canary/hpc/run`` holds the work lane while its batches wait on the scheduler.
* **Fixed environment.**  Work runs in the server's environment as of
  ``canary server start``; changing modules means restarting the server.  A request can
  only add variables (``env``).
* **Shared filesystem.**  Until the HTTP binding exists, callers and the server meet in the
  workspace's files.
* **Access control** is the permissions of ``inbox/``: anyone who can create files there can
  submit requests, which run as the server's user.
* **A read cannot always be stopped.**  Past ``server:read_timeout`` a read gets its
  ``failed`` result and its database query is interrupted, but a read busy elsewhere keeps
  its thread until it returns.
* **No live progress table.**  Work output is the text a terminal would show, in
  ``requests/<id>/stdout``.
* **Not through the server:** in-process Python runs (``_canary.app.run_request.run``) and local
  ``canary`` commands; they work on the workspace directly.
