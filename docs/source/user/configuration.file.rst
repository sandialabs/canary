.. _configuration-file:

Configuration file
==================

In addition to the command line, configuration variables can be explicitly set ``yaml`` formatted files.  ``nvtest`` first looks for the "global" configuration in ``~/.config/nvtest/config.yaml``.  You can modify the location of this file by setting the ``NVTEST_CONFIG_HOME`` or ``XDG_CONFIG_HOME`` environment variables, in which case the configuration will be found in ``$NVTEST_CONFIG_HOME/config.yaml`` or ``$XDG_CONFIG_HOME/nvtest/config.yaml``.  Setting ``NVTEST_CONFIG_HOME=null`` will cause ``nvtest`` to ignore this configuration scope.

The next place ``nvtest`` looks is ``./nvtest.yaml``.  Values in this "local" configuration scope take precedence over values in the global configuration scope.

Configuration scope precedence
------------------------------

Values from the global, local, and command line configuration scopes overwrite values in the previous scope.

.. note::

   There is also a read-only "session" configuration scope that is written when a test session is created.  The values therein are set by the configuration when the session is launched and take precedence in future invocations.
