.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-agent:

Bootstrapping agent-facing guidance
===================================

``canary agent`` helps you write agent-facing bootstrap files that explain how
to use Canary in a workspace. This is useful when you want an automated coding
agent or assistant to understand Canary's capabilities, available skills, and
recommended workflows before it starts making changes.

Use this page for the common workflow. For the complete generated command
reference, see :ref:`canary agent <canary-agent>`.

What ``canary agent`` does
--------------------------

Today, the main subcommand is ``canary agent bootstrap``. It writes managed
bootstrap content for an agent target layout.

This bootstrap content is intended to:

- introduce Canary's execution model and core concepts
- point the agent at installed capability and skill data
- provide short, task-oriented guidance for common Canary workflows
- steer the agent toward ``canary query`` and ``canary learn`` before raw
  workspace inspection or ad hoc SQL

Basic usage
-----------

The default bootstrap target is ``generic``:

.. code-block:: console

   canary agent bootstrap

Explicit target selection looks like this:

.. code-block:: console

   canary agent bootstrap generic
   canary agent bootstrap opencode

Supported targets
-----------------

``generic``
   Writes a general-purpose bootstrap file for environments that want plain
   agent-facing Canary guidance without editor-specific layout assumptions. The
   generated files live under ``.agent/canary/``.

``opencode``
   Writes the managed files expected by the OpenCode-oriented workflow under
   ``.opencode/skills/`` and also writes the generic ``.agent/canary/``
   guidance so non-OpenCode agents still have a harness-neutral Canary entry
   point.

Choose the target that matches the environment where the agent will be running.

Useful flags
------------

Use ``--brief`` to write only the concise bootstrap file:

.. code-block:: console

   canary agent bootstrap generic --brief

Use ``--force`` to overwrite existing managed files:

.. code-block:: console

   canary agent bootstrap opencode --force

When to run it
--------------

Run ``canary agent bootstrap`` when:

- you are introducing Canary into a workspace that will be used by an agent
- you want to refresh managed agent guidance after upgrading Canary
- you want the workspace to advertise the installed Canary skills and capabilities clearly

This is especially helpful before asking an agent to debug runs, inspect query
data, or extend Canary behavior.

How it fits with ``learn`` and ``query``
----------------------------------------

``canary agent`` prepares the workspace-facing guidance. The other two agent-
centered commands then expose the installed knowledge directly:

- use :doc:`/user/usage.learn` to inspect the capability and skill datasets
- use :doc:`/user/usage.query` to access those datasets through the ``-c`` and
  ``--skills`` query shortcuts while also inspecting workspace data

Suggested workflow
------------------

For a new agent-oriented workspace, the normal sequence is:

1. Run ``canary agent bootstrap`` for the appropriate target.
2. Inspect what Canary knows with ``canary learn capabilities --list .`` and
   ``canary learn skills --list .`` or ``canary query --skills . --list``.
3. Use ``canary query -c ...`` or ``canary query --skills ...`` inside active
   debugging or extension-authoring loops.
4. Prefer ``canary query`` subcommands over direct reads of ``.canary`` files
   or direct SQLite inspection unless no structured query path exists for the
   information you need.

See also
--------

- :doc:`/user/usage.learn` for installed capabilities and skills
- :doc:`/user/usage.query` for knowledge shortcuts and structured workspace queries
- :ref:`canary agent <canary-agent>` for the generated command reference
