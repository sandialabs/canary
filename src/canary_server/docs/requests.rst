.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Requests
========

A request is a canary command line.  ``canary --server run -k fast tests`` and
``canary server post`` both produce one:

.. code-block:: json

   {"command": "run", "args": ["-k", "fast", "tests"]}

``post`` fills in what is missing:

``id``
   A sortable request id, ``YYYYMMDDTHHMMSS-xxxxxx``.
``options``
   Global options placed before the command, e.g. ``["-p", "myplugin"]``.  Default: none.
``cwd``
   The working directory the command runs in.  Default: the current directory.  It must
   mean the same thing on the server's machine (a shared filesystem).
``env``
   Environment variables the command runs with, laid over the server's own environment.
   Default: the client's ``PATH``, ``PYTHONPATH``, ``LD_LIBRARY_PATH``, ``VIRTUAL_ENV`` and
   ``CANARY_*`` variables.
``user``, ``host``, ``submitted``, ``client_version``
   Who sent it, from where, and when.

How a request runs
------------------

Requests run **one at a time, in arrival order**.  Each gets the machine's whole resource
pool, as a local run does; the jobs within a request still run in parallel.

The server runs each request as a child process, ``canary [options] command [args]``, in
the request's working directory.  The child is an ordinary top-level canary run: it owns
its configuration, writes its own results to the workspace database, and its output goes
to the request's ``stdout`` and ``stderr`` files.

A request moves through these states:

``queued``
   Waiting for its turn; ``position`` says how many requests are ahead (1 = next).
``running``
   The child is running; ``pid`` is its process id.
``done``
   The child exited; ``returncode`` is its exit code.
``cancelled``
   Cancelled before or while running.
``failed``
   The server could not run it (e.g. its working directory does not exist on the server's
   machine), or the server exited while it was running.

Cancelling a running request sends SIGINT to the child's process group, then SIGTERM and
SIGKILL if it does not stop.

Files
-----

.. code-block:: text

   .canary/var/server/
     server.lock          held by the running server
     server.json          pid, host, start time, heartbeat, version
     stop                 written by `canary server stop`
     inbox/               the queue (ready/, claimed/, failed/, tmp/)
     requests/<id>/
       request.json       the request
       status.json        state, position, pid, returncode, reason, times
       stdout, stderr     the command's output
       cancel             written by `canary server cancel`

Files are written atomically (write, then rename), so a reader never sees a partial file.

Restarts and crashes
--------------------

The server rewrites ``server.json`` every 2 seconds.  A server whose heartbeat is more than
10 seconds old, or whose process is gone (checked on the same host), is dead: clients refuse
to queue new requests for it, and the next ``canary server start`` takes over its lock.  On
start, a request the dead server was running is marked ``failed``; requests it had claimed
but not started go back in the queue.
