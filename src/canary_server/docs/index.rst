.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _canary_server:

Server Extension
================

The ``canary_server`` extension runs a **command server for a workspace**.  You start the
server once, on the machine that should do the work, and then send it canary commands from
anywhere the workspace is visible -- another terminal, another machine on the same shared
filesystem, or an agent.  The server runs them one at a time, each exactly as the
corresponding ``canary`` command would run locally.

All communication is through files in the workspace (``.canary/var/server/``): there are no
sockets and no network protocol.  A client finds the server by finding the workspace, the
same way every canary command does.

Quick Start
-----------

On the machine that should run the jobs, in the workspace:

.. code-block:: console

   $ module load my-app             # requests run in the environment the server starts in
   $ canary server start &          # blocks; background it with the shell

From any terminal or machine that sees the workspace:

.. code-block:: console

   $ canary --connect=. run -k fast tests    # queued on the server; prints the request id
   $ canary server wait ID                   # follow it here (the server's terminal shows it too)
   $ canary server status                    # the server, its running request, the queue
   $ canary server stop

An agent sends the same request as data and checks back later:

.. code-block:: console

   $ canary server post '{"command": "run", "args": ["-k", "fast", "tests"]}'
   {"id": "20261118T153434-eafc61"}
   $ canary server wait 20261118T153434-eafc61 --quiet; echo $?
   0

.. note::

   ``canary_server`` is a **built-in** canary extension, included in the ``canary-wm``
   package.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   commands
   requests
   agents
   limitations

See Also
--------

- :doc:`/user/basics.workspace`: Canary workspaces
- :doc:`/extensions/plugins`: Canary plugin system
- :doc:`/extensions/exts/canary_hpc/index`: ``canary_hpc``, which ``canary --connect=WHERE hpc run`` drives
