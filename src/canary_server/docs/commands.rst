.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Commands
========

Every command acts on the server of the current workspace (found from the current
directory, ``-C DIR`` or ``--canary-dir``).

Running the server
------------------

``canary server start``
   Runs the server in the foreground until it is stopped, logging each request as it starts
   and finishes.  To run it in the background, use the shell, redirecting its output if you
   like: ``canary server start > server.log 2>&1 &``.  To keep it running after the
   terminal closes, use ``nohup`` (or ``tmux``, ``screen``, or a batch job).  A second
   server for the same workspace is refused.

``canary server stop``
   Asks the server to stop, from any machine that sees the workspace, and waits for it.  The
   running request is interrupted; queued requests stay queued for the next server.
   SIGINT, SIGTERM and SIGHUP stop the server in the same way.

``canary server status [--json]``
   Shows whether the server is alive (pid, host, version), the running request, and the
   queue.  Exits 0 if the server is alive, 1 otherwise.

Sending commands
----------------

``canary --server COMMAND ARGS...``
   Runs ``canary COMMAND ARGS...`` on the server instead of here, streams its output, and
   exits with its exit code.  The server runs these commands:

   * ``run``, ``exec``, ``collect`` and ``select``;
   * ``hpc run`` (other ``hpc`` subcommands run locally).

   Global options before the command (``-p``, ``-o``, ``-e`` ...) are passed along; ``-C``
   is replaced by the working directory it selects.  Ctrl-C cancels the request; a second
   Ctrl-C stops following and leaves the request on the server.  ``--server`` with any
   other command, or with no server running, is an error.

``canary server post JSON [--wait]``
   Submits a request given as JSON (``-`` reads it from stdin), prints ``{"id": ...}`` and
   returns.  ``--wait`` follows the request like ``--server`` does.  See :doc:`requests`
   for the format.

Following up on a request
-------------------------

``canary server get ID [--output]``
   Prints the request's record as JSON: what it runs, its ``state``, its ``position`` in the
   queue, its ``returncode``, its times, and the paths of its ``stdout`` and ``stderr``.
   ``--output`` prints the captured output instead.

``canary server wait ID [--quiet]``
   Follows the request until it finishes, printing its output (unless ``--quiet``), and
   exits with its exit code.

``canary server cancel ID``
   Cancels a queued request (it never runs) or interrupts a running one.

Exit codes
----------

A finished request reports the exit code of its canary command.  A cancelled request
reports 130 and a failed one (the server could not run it, or exited while running it)
reports 1.

Protected operations
--------------------

While a server is running for a workspace, ``canary rm`` and ``canary run -w`` (which
remove the workspace) are refused: stop the server first.  If the workspace disappears
anyway, the server notices, kills the running request and exits without writing anything.
