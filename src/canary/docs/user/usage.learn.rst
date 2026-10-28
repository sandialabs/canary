.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-learn:

Learning installed capabilities and skills
==========================================

``canary learn`` exposes machine-readable guidance shipped by Canary core and by
installed plugins. It is the main command for discovering what Canary knows how
to do and what packaged guidance is available for users, extensions, and agents.

Use this page for the common workflows. For the complete generated command
reference, see :ref:`canary learn <canary-learn>`.

Capabilities vs skills
----------------------

``canary learn`` exposes two related but distinct datasets:

- **Capabilities** describe behavior, interfaces, and concepts Canary supports.
  They answer questions like "how do hooks work?" or "what does the core model look like?"
- **Skills** package task-oriented guidance, usually for an agent or advanced
  user, such as how to debug a Canary run or how to extend a specific plugin.

If you want source-grounded product knowledge, start with capabilities. If you
want a reusable playbook for a task, start with skills.

List what is available
----------------------

To discover installed topics, list from the root:

.. code-block:: console

   canary learn capabilities --list .
   canary learn skills --list .

This is the fastest way to see which core namespaces and plugin namespaces are
available in your current installation.

Read capability data
--------------------

Use ``canary learn capabilities`` when you want to inspect structured knowledge
 about Canary behavior:

.. code-block:: console

   canary learn capabilities .
   canary learn capabilities core.overview
   canary learn capabilities hooks
   canary learn capabilities ext --list

Use ``--terse`` when you want compact JSON for scripts or tooling:

.. code-block:: console

   canary learn capabilities core.overview --terse

Read skill data
---------------

Use ``canary learn skills`` when you want task-oriented guidance:

.. code-block:: console

   canary learn skills .
   canary learn skills core.canary-orientation
   canary learn skills --list core

This is especially useful when working with agent bootstrap flows or when a
plugin ships task-specific guidance alongside its capability data.

When to use ``learn`` vs ``query`` shortcuts
--------------------------------------------

``canary query`` exposes convenience flags that forward into the same knowledge
data:

.. code-block:: console

   canary query -c core.overview
   canary query --skills core.canary-orientation

Use ``canary learn`` when knowledge discovery is your main task. Use the query
shortcuts when you are already in a query-centric workflow and want quick access
to capability or skill data.

How plugins contribute knowledge
--------------------------------

Installed plugins can contribute their own capability and skill datasets. This
is why ``canary learn`` can expose extension-specific topics in addition to the
core Canary topics.

If you are authoring a plugin and want to understand how these datasets are
provided, see :doc:`/extensions/authoring`.

See also
--------

- :doc:`/user/usage.query` for the ``-c`` and ``--skills`` query shortcuts
- :doc:`/user/usage.agent` for agent bootstrap workflows that consume this guidance
- :ref:`canary learn <canary-learn>` for the generated command reference
