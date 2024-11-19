.. _configuration-file:

Configuration file
==================

In addition to the command line, configuration variables can be explicitly set ``toml`` formatted files in:

- ``~/.nvtest``.
- ``./nvtest.toml``

``~/.nvtest`` is the "global" configuration scope while ``./nvtest.toml`` is the "local" configuration scope.  The order of precedence for configuration scopes is

1. Command line
2. Local configuration
3. Global configuration

.. note::

   There is also a "session" configuration scope that is written when a test session is created.  The values therein are set by the local configuration when the session is launched and take precedence in future invocations.
