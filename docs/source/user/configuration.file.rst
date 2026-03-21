.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _configuration-file:

Configuration file
==================

In addition to the command line, configuration variables can be explicitly set ``yaml`` formatted files.  ``canary`` first looks for the "global" configuration in ``~/.config/canary/config.yaml``.  You can modify the location of this file by setting the ``CANARY_CONFIG_DIR`` or ``XDG_CONFIG_HOME`` environment variables, in which case the configuration will be found in ``$CANARY_CONFIG_DIR/config.yaml`` or ``$XDG_CONFIG_HOME/canary/config.yaml``.  Setting ``CANARY_CONFIG_DIR=null`` will cause ``canary`` to ignore this configuration scope.

The next place ``canary`` looks is ``.canary/config.yaml``.  Values in this "local" configuration scope take precedence over values in the global configuration scope.

Configuration scope precedence
------------------------------

Values from the global, local, and command line configuration scopes overwrite values in the previous scope.
