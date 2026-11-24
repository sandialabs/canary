.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_server:

The Request Server
==================

``canary server`` runs a **request server for a workspace**.  You start it
once, on the machine that should do the work.  Callers -- another terminal, another
machine on the same shared filesystem, a CI job or an agent -- then hand it typed
requests and read the results.  Callers need **nothing installed**: no canary, no Python.
A POSIX shell is enough.

Requests travel as files in the workspace (``.canary/var/server/``).  Each request names
an HTTP-style route (``/canary/run``, ``/canary/status``, ...) and carries a JSON body,
so the same routes and documents will serve an HTTP binding later.

Quick Start
-----------

On the machine that should run the jobs, in the workspace:

.. code-block:: console

   $ module load my-app             # work runs in the environment the server starts in
   $ canary server start &          # blocks; background it with the shell

From anywhere that sees the workspace, with only a shell, use the server's ``carl`` (a
small curl-like script the server installs in ``.canary/share/``):

.. code-block:: console

   $ /path/to/ws/.canary/share/carl POST file:///path/to/ws/canary/run -d '{"pathspec": ["tests"]}'
   carl: submitted carl-20261124T101500-4242
   {"version": 1, "id": "carl-20261124T101500-4242", "path": "/canary/run",
    "status_code": 200, "state": "done", "data": {"exit_code": 0}, ...}

or the files themselves (this is all ``carl`` does):

.. code-block:: console

   $ S=/path/to/ws/.canary/var/server
   $ echo '{"path": "/canary/run", "request": {"pathspec": ["tests"]}}' > $S/inbox/r1.json.tmp
   $ mv $S/inbox/r1.json.tmp $S/inbox/r1.json
   $ until [ -f $S/requests/r1/result.json ]; do sleep 1; done
   $ cat $S/requests/r1/result.json
   {"version": 1, "id": "r1", "path": "/canary/run", "status_code": 200, "state": "done",
    "data": {"exit_code": 0}, ...}

Stop the server with ``canary server stop`` (on any machine that sees the workspace).

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   usage.server.commands
   usage.server.requests
   usage.server.endpoints
   usage.server.agents
   usage.server.limitations

See Also
--------

- :doc:`/user/basics.workspace`: Canary workspaces
- :doc:`usage.hpc`: HPC runs, which ``/canary/hpc/run`` drives
