.. _configuration-cli:

Setting configuration variables on the command line
===================================================

Use yaml path syntax to set any of the above variables.  For example,

.. code-block:: console

   nvtest -c machine:cpus_per_node:20 -c config:log_level:DEBUG SUBCOMMAND [OPTIONS] ARGUMENTS

To set environment variables do

.. code-block:: console

   nvtest -e VAR1=VAL1 -e VAR2=VAL2 SUBCOMMAND [OPTIONS] ARGUMENTS

.. note::

   Configuration settings set on the command line take precedence over environment configuration settings.
