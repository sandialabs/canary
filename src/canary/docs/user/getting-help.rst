.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _intro-getting-help:

Getting help
============

``canary`` has several :ref:`subcommands <canary>`.  To get the list of subcommands, issue

.. doc-run::
   :script: [{"args": "canary -h"}]


To get help on an individual subcommand, issue, for example:

.. doc-run::
   :script: [{"args": "canary run -h"}]

For result triage and workspace inspection, the most useful commands to discover are:

- ``canary query failures`` for grouped failure signatures
- ``canary query compare`` for cross-session regression comparison
- ``canary query jobs --with logs[:N]`` for batch log metadata
- ``canary query job JOBID --blockers`` for blocked dependency explanation
- ``canary query job JOBID --missing-inputs`` for staged-input debugging

Machine-readable capability and skill help is also available via ``canary learn``.

See also:

- :doc:`/user/usage.query` for structured workspace queries
- :doc:`/user/usage.learn` for capabilities and skills
- :doc:`/user/usage.agent` for agent bootstrap workflows
