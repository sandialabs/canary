.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Commands and Configuration
==========================

``canary server`` has two commands, both for the operator.  Callers never run canary:
they use the files described in :doc:`usage.server.requests`.

``canary server start [-w]``
   Serves the workspace found from the current directory, creating one here if there is
   none, as ``canary run`` does.  ``-w`` removes the workspace located exactly here and
   starts with a fresh one (never an enclosing workspace, and never one a live server
   owns).  Runs in the foreground until stopped, printing each request as it starts and
   finishes, with work requests' output in between.  Background it with the shell
   (``canary server start > server.log 2>&1 &``); to keep it running after the terminal
   closes, use ``nohup``, ``tmux``, ``screen`` or a batch job.  A second server for the
   same workspace is refused.  At start it installs ``.canary/share/carl``, the curl-like
   client callers can run with only ``sh`` (see :doc:`usage.server.agents`).

``canary server stop``
   Asks the server to stop, from any machine that sees the workspace, and waits for it.
   The running work request and any reads in progress end ``failed``; queued work stays
   queued for the next server.  SIGINT, SIGTERM and SIGHUP stop the server the same way.

While a server runs -- or any ``canary run``, ``collect``, ``select`` or ``rebaseline`` --
the workspace is *in use* (a shared ``flock`` on ``.canary/in-use``), and ``canary rm``
and ``canary run -w`` refuse to remove it.  The lock goes away with its holder, however
it exits, so a crashed server never leaves the workspace locked.  If the workspace
disappears anyway, the server kills the running request and exits without recreating
anything.

Environment
-----------

Work runs in the server's environment as of ``canary server start`` (modules, ``PATH``,
``LD_LIBRARY_PATH``, ...).  Nothing from a caller's environment is carried; a request
adds variables only through its envelope's ``env``.  Load what the jobs need *before*
starting the server.

Configuration
-------------

In any canary configuration file (see :doc:`/user/configuration`):

.. code-block:: yaml

   server:
     read_workers: 4      # reads run concurrently in this many threads
     read_timeout: 300    # seconds a read may run once started
     retain_days: 7       # finished requests older than this are pruned at start
     allowed_roots:       # trees outside the workspace requests may name (default: none)
       src: /projects/app/src

The server reads them when it starts.  A request may name filesystem paths (a run's
``pathspec``, ``/canary/collect``'s ``roots``, ...) only inside the workspace or under an
``allowed_roots`` entry, symbolic links resolved; anything else is refused with ``403``.
Results show a job's absolute paths (``file_root``, ``exec_dir``) relative to the
workspace, as ``name:relative/path`` under an allowed root, and anywhere else only by their
last component (``…/suite``), so no server path is published that a caller did not name.
