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
