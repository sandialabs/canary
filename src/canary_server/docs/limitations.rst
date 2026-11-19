.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Limitations
===========

* **One request at a time.**  Requests do not share the resource pool, so they run
  sequentially.  This costs little for local runs (each fills the machine), but
  ``hpc run`` holds the server while its batches wait on the scheduler.
* **Fixed environment.**  Requests run in the server's environment as of
  ``canary server start``; changing modules means restarting the server.  Only
  ``canary server post`` can add variables (``env``); there is no ``--env`` option yet.
* **Shared filesystem.**  Clients and server communicate through the workspace's files;
  paths in a request must mean the same thing on the server's machine.
* **Access control** is the workspace directory's permissions: anyone who can write to
  ``.canary/var/server/`` can submit requests.
* **No live status table.**  ``canary server wait`` and the server's terminal show the command's text output;
  the live progress display of a local run is not shown.
* **In-process Python runs** (``_canary.api.run.run``) do not go through the server.
