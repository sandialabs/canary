.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Commands
========

Every command acts on the server of a workspace: the one found from ``--connect=WHERE``
if given, else the one found from the current directory (or ``-C DIR``, ``--canary-dir``).

``--connect=WHERE``
   WHERE is where the workspace search starts: any path inside the workspace tree (or the
   anchor directory above ``.canary``), or a ``file://`` URL for one.  ``--connect=.``
   uses the workspace you are in.  Unlike ``-C``, it does not change your working
   directory: relative paths in the command still mean what they mean where you typed
   them.  Other URL schemes are not supported.

Running the server
------------------

``canary server start``
   Runs the server in the foreground until it is stopped, printing each request as it
   starts and finishes, with the request's output in between.  To run it in the background, use the shell, redirecting its output if you
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

``canary --connect=WHERE COMMAND ARGS...``
   Queues ``canary COMMAND ARGS...`` on that workspace's server, prints the request id (with
   how to follow and cancel it) and returns at once.  The server prints the command's
   output on its own terminal and keeps it with the request; ``canary server wait ID``
   follows it from anywhere and exits with the command's exit code.  The server runs these
   commands:

   * ``run``, ``exec``, ``collect`` and ``select``;
   * ``hpc run`` (other ``hpc`` subcommands run locally).

   Global options before the command (``-p``, ``-o``, ``-e`` ...) are passed along; ``-C``
   is replaced by the working directory it selects.  ``--connect`` with any other command,
   or with no server running, is an error.

   .. code-block:: console

      $ cd ~/proj/tests
      $ canary --connect=. run fast/                 # from inside the workspace tree
      canary: request 20261118T153434-eafc61 queued on the server (position 1)
        follow: canary server wait 20261118T153434-eafc61
        cancel: canary server cancel 20261118T153434-eafc61
      $ canary --connect=/scratch/ws run fast/       # runs ~/proj/tests/fast on /scratch/ws's server
      $ canary --connect=/scratch/ws server status   # the server subcommands accept it too

``canary server post REQUEST [--wait]``
   Submits a request -- JSON text (anything starting with ``{``), a file holding it, or ``-``
   to read it from stdin -- prints ``{"id": ...}`` and
   returns.  ``--wait`` follows the request until it finishes (``post`` then ``wait``).  See :doc:`requests`
   for the format.

Following up on a request
-------------------------

``canary server get ID [--output]``
   Prints the request's record as JSON: what it runs, its ``state``, its ``position`` in the
   queue, its ``returncode``, its times, and the paths of its ``stdout`` and ``stderr``.
   ``--output`` prints the captured output instead.

``canary server wait ID [--quiet]``
   Follows the request until it finishes, printing its output (unless ``--quiet``), and
   exits with its exit code.  Ctrl-C cancels the request; a second Ctrl-C stops following
   and leaves the request on the server.

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
