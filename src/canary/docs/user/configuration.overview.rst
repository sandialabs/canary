.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _configuration-overview:

Overview
========

Additional configuration is not required to run ``canary``.  To see the current configuration, issue

.. doc-run::
   :script: [{"args": "canary config show"}]

Configuration variables can be set on the command line or read from a
configuration file.

Configuration sources and precedence
--------------------------------------

``canary`` loads configuration from multiple sources in order of increasing
precedence (later sources override earlier ones):

1. **System defaults** — built-in default values compiled into ``canary``
2. **Site configuration** — ``/etc/canary/config.yaml`` (system-wide)
3. **Global configuration** — ``~/.config/canary/config.yaml`` (user-specific)
4. **Local configuration** — ``.canary/config.yaml`` (workspace-specific)
5. **Environment variables** — ``CANARYCFGFILE`` or ``CANARYCFG64``
6. **Command line** — ``-c`` and ``-e`` options (highest precedence)

Use ``canary config show`` at any time to inspect the resolved effective
configuration after all sources have been merged.
