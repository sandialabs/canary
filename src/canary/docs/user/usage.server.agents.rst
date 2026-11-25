.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Callers and Agents
==================

A caller drops a request, waits for its result, and reads it.  The quickest way is the
workspace's ``carl``, which works like curl:

.. code-block:: sh

   CARL=/path/to/ws/.canary/share/carl
   WS=file:///path/to/ws

   $CARL POST $WS/canary/run -d '{"pathspec": ["tests"], "only": "all"}'   # wait, print the result
   $CARL POST $WS/canary/query/failures -s                                 # a read
   $CARL POST $WS/canary/run -d @request.json -H 'Idempotency-Key: nightly-1' -m 3600
   $CARL GET  $WS/requests/nightly-1                                       # its result (or status)
   $CARL POST $WS/requests/nightly-1/cancel
   $CARL POST $WS/canary/run --cwd tests --env OMP_NUM_THREADS=4 -d '{"pathspec": ["."]}'

The route is the URL's path after the workspace; ``-d`` is the body (``@file``, ``@-``);
``-f`` exits 22 on an error result; ``-m`` stops waiting (exit 28; the request goes on);
Ctrl-C cancels; no server running is exit 7.  ``carl --help`` lists the rest.  ``PUT`` is
the same as ``POST``; a ``POST`` to the workspace itself takes a whole envelope.

Without ``carl`` it is still only files.  This is all of it, in POSIX shell:

.. code-block:: sh

   S=/path/to/ws/.canary/var/server          # the server directory

   submit() {  # ID JSON
       printf '%s\n' "$2" > "$S/inbox/$1.json.tmp" && mv "$S/inbox/$1.json.tmp" "$S/inbox/$1.json"
   }
   result() {  # ID: wait for the result, print it
       until [ -f "$S/requests/$1/result.json" ]; do sleep 1; done
       cat "$S/requests/$1/result.json"
   }

   id="run-$(date +%Y%m%dT%H%M%S)-$$"
   submit "$id" '{"path": "/canary/run", "request": {"pathspec": ["tests"], "only": "all"}}'
   tail -f "$S/requests/$id/stdout" &         # optional: watch the output
   result "$id"

   submit s1 '{"path": "/canary/query/failures"}'
   result s1                                  # the latest session's failed jobs

   touch "$S/requests/$id/cancel"             # cancel a request

Practical notes:

* Make ids unique: a reused id is rejected (``409``).  A timestamp plus ``$$`` or
  ``uuidgen`` will do.
* Check the server is alive before relying on it: ``server.json`` exists and its
  ``beat`` changes within a few seconds.  Requests dropped while no server runs wait in
  ``inbox/``.
* Look before you leap: ``/canary/help`` lists every route, what it does and its fields;
  ``/canary/schema`` has each body's JSON schema.
* The skills say ``canary query -c TOPIC`` and ``canary learn skills SKILL``; without
  canary, ``/canary/learn/capabilities`` and ``/canary/learn/skills`` (``{"topic":
  ...}``) return the same data.  The ``canary-server`` skill maps the other commands to
  routes.
* Read ``data.exit_code`` for work, not only ``state``: a run whose tests fail is still
  ``done``.  ``7`` means nothing ran (e.g. rerunning tests that passed without
  ``only: "all"``).  Any other non-zero code is a sum of bits, one per kind of job
  that did not pass: 2 diffed, 4 timed out, 8 failed, 16 cancelled, 32 did not finish, 64
  another status; 1 and 3 mean canary itself failed.  ``/canary/help`` lists them as
  ``exit_codes``.
* ``cwd`` and paths in the body are relative to the anchor: they mean the same on every
  machine, wherever each mounts the share.  Never send an absolute path: the server
  resolves it on its own machine, where the workspace may be mounted elsewhere (a missing
  one is ``400 ... no such file or directory``).
* Reads (status, queries) answer while work runs; work requests wait their turn.
