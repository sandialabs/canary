.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Requests
========

A request is a canary command line.  ``canary --connect=. run -k fast tests`` and
``canary server post`` both produce one:

.. code-block:: json

   {"command": "run", "args": ["-k", "fast", "tests"]}

``post`` fills in what is missing:

``id``
   A sortable request id, ``YYYYMMDDTHHMMSS-xxxxxx``.
``options``
   Global options placed before the command, e.g. ``["-p", "myplugin"]``.  Default: none.
``cwd``
   The working directory the command runs in, relative to the workspace anchor (the
   directory holding ``.canary``) or absolute.  Default: ``"."``, the anchor;
   ``--connect`` records your current directory relative to the anchor.  See
   `Working directory and paths`_.
``env``
   Variables to set on top of the server's environment, e.g. ``{"MY_FLAG": "1"}``.
   Default: none.  Only ``canary server post`` can set it; see `Environment`_.
``user``, ``host``, ``submitted``, ``client_version``
   Who sent it, from where, and when.

Environment
-----------

A request runs in the **server's environment, as it was when** ``canary server start``
**ran**: its modules, ``PATH``, ``LD_LIBRARY_PATH``, and everything else.  Nothing from the
client's environment is carried.  So prepare the environment where the server starts:

.. code-block:: console

   hpc-login$ module load my-app
   hpc-login$ canary server start &
   desktop$   canary --connect=. run some_problem      # runs with my-app loaded

A request cannot change modules; restart the server in a new environment to change them
(or have the test load what it needs).  To set individual variables for one request, post
it with ``env``:

.. code-block:: console

   $ canary server post '{"command": "run", "args": ["tests"], "env": {"MY_FLAG": "1"}}'

Working directory and paths
---------------------------

The request records the client's working directory (after any ``-C``) **relative to the
workspace anchor**, the directory holding ``.canary``; the server starts the command in
that directory under *its* anchor (and sets ``$PWD`` to it).  Path arguments are passed as
typed, never made absolute.  So relative paths on the command line mean what they meant
where you typed them -- even when the server's machine mounts the filesystem somewhere else:

.. code-block:: console

   # here the share is /projects; on hpc-login it is /gpfs/me/Projects/dev
   hpc-login$ cd /gpfs/me/Projects/dev/src/canary && canary server start &
   desktop:/projects$ canary -C src/canary --connect=. run ./examples
   # recorded cwd ".", run on hpc-login in /gpfs/me/Projects/dev/src/canary: ./examples there

From outside the workspace tree the recorded directory goes up and across
(``../../home/me/proj``); that maps as long as both directories are on the same share,
mounted the same way relative to each other:

.. code-block:: console

   desktop:~/proj$ canary --connect=/path/to/ws run foo         # runs ~/proj/foo
   desktop:~/proj$ canary --connect=. -C /path/to/ws run foo    # -C moved you: /path/to/ws/foo

The command always works on the **server's** workspace, wherever its working directory
is, and its arguments are interpreted there (the client does not parse them).  So tags,
job ids and reruns refer to the server's workspace:

.. code-block:: console

   $ canary --connect=/path/to/ws run --only=failed    # rerun what failed in /path/to/ws
   $ canary --connect=/path/to/ws run 27a7685          # rerun one job of /path/to/ws

A request whose directory does not exist on the server's machine fails at once.  An
absolute ``cwd`` posted with ``canary server post`` is used as is.  File paths are
interpreted on the shared filesystem; *search* paths -- ``PATH``,
``LD_LIBRARY_PATH``, ``PYTHONPATH``, ``MODULEPATH`` -- come from the server's environment
(`Environment`_).

How a request runs
------------------

Requests run **one at a time, in arrival order**.  Each gets the machine's whole resource
pool, as a local run does; the jobs within a request still run in parallel.

The server runs each request as a child process, ``canary [options] command [args]``, in
the request's working directory.  The child is an ordinary top-level canary run: it owns
its configuration, writes its own results to the workspace database, and its output goes
to the server's terminal and to the request's ``stdout`` and ``stderr`` files.

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
