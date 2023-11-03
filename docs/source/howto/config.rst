Configuration settings
======================

Additional configuration is not required.  To see the current configuration, issue

.. code-block:: console

   nvtest config show

Configuration variables can be set on the command line or read from a configuration file.

Configuration file
------------------

You can explicitly set configuration variables in:

- ``./nvtest.cfg``;
- ``~/.config/nvtest.cfg``; and
- ``~/.nvtest.cfg``.

The first found is used.  Basic configuration settings are:

.. code-block:: ini
[config]
debug = false
log_level = int

[variables]
key = "value"  # environment variables to set for the test session

[machine]
sockets_per_node = 1
cores_per_socket = N  # default computed from os.cpu_count()
cpu_count = N  # default computed from os.cpu_count()

Setting configuration variables on the command line
---------------------------------------------------

Use yaml path syntax to set any of the above variables.  For example,

.. code-block:: console

   nvtest -c machine:cpu_count:20 -c config:log_level:0 SUBCOMMAND [OPTIONS] ARGUMENTS

To set environment variables do

.. code-block:: console

   nvtest -e VAR1=VAL1 -e VAR2=VAL2 SUBCOMMAND [OPTIONS] ARGUMENTS
