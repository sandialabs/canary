.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _configuration-cli:

Setting configuration variables on the command line
===================================================

Use yaml path syntax to set any of the ``canary`` configuration variables.  For example,

.. code-block:: console

   canary -c config:debug:true -c config:log_level:DEBUG SUBCOMMAND [OPTIONS] ARGUMENTS

To set environment variables do

.. code-block:: console

   canary -e VAR1=VAL1 -e VAR2=VAL2 SUBCOMMAND [OPTIONS] ARGUMENTS

.. note::

   Configuration settings set on the command line take precedence over environment configuration settings.

Persisting configuration with ``canary config set``
------------------------------------------------------

To write a setting permanently to the local workspace configuration or the global
user configuration, use ``canary config set``:

.. code-block:: console

   # Write to .canary/config.yaml (workspace-local)
   canary config set --local run:timeout:default 600.0

   # Write to ~/.config/canary/config.yaml (user-global)
   canary config set --global plugins "[canary_hpc]"

The ``--local`` flag writes to the workspace's ``.canary/config.yaml``; ``--global``
writes to the user-level ``~/.config/canary/config.yaml``.  Both flags require a
``KEY VALUE`` pair where the key uses colon-separated YAML path notation.
