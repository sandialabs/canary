.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Agents
======

An agent does not need to assemble a command line: it posts the request as JSON, keeps the
id, and checks back.

.. code-block:: console

   $ canary server post '{"command": "run", "args": ["--only", "failed", "tests"]}'
   {"id": "20261118T153434-eafc61"}

   $ canary server post request.json          # or a file holding the request (- for stdin)

   $ canary server get 20261118T153434-eafc61
   {"id": "20261118T153434-eafc61", "command": "run", "state": "running", "pid": 564544, ...}

   $ canary server wait 20261118T153434-eafc61 --quiet; echo $?
   8

   $ canary server get 20261118T153434-eafc61 --output | tail -3

Requests run in the server's environment (from when it started); nothing from yours is
carried.  Set variables for one request explicitly:
``{"command": "run", "args": ["tests"], "env": {"MY_FLAG": "1"}}``.

From outside the workspace tree, add ``--connect=WHERE``
(``canary --connect=/scratch/ws server post ...``).

Results are in the workspace as for any run: read them with ``canary status --json`` and
``canary query`` (these always run locally and never go through the server).

Practical notes:

* ``canary run PATH`` defaults to ``--only not_pass``: a request to rerun something that
  already passed runs nothing (exit code 7).  Pass ``--only all`` to rerun everything.
* Use ``canary server status --json`` to see whether a server is alive and how long the
  queue is before posting.
* ``hpc run`` keeps the server busy until the HPC run finishes (its
  batches wait on the scheduler), so other requests wait behind it.
