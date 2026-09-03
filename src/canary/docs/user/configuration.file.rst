.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _configuration-file:

Configuration file
==================

In addition to the command line, configuration variables can be explicitly set ``yaml`` formatted files.  ``canary`` first looks for the "global" configuration in ``~/.config/canary/config.yaml``.  You can modify the location of this file by setting the ``CANARY_CONFIG_DIR`` or ``XDG_CONFIG_HOME`` environment variables, in which case the configuration will be found in ``$CANARY_CONFIG_DIR/config.yaml`` or ``$XDG_CONFIG_HOME/canary/config.yaml``.  Setting ``CANARY_CONFIG_DIR=null`` will cause ``canary`` to ignore this configuration scope.

The next place ``canary`` looks is ``.canary/config.yaml``.  Values in this "local" configuration scope take precedence over values in the global configuration scope.

Configuration scope precedence
------------------------------

Values from the global, local, and command line configuration scopes overwrite values in the
previous scope.

.. _canary-root-anchor:

Spec ID anchoring for non-VCS workflows
----------------------------------------

``canary`` generates a stable, content-independent ID for each job based on its family name,
repo-relative file path, and parameters.  To compute the repo-relative path it walks up the
directory tree from the test file looking for an anchor directory in this order:

1. ``.git`` — a Git repository root
2. ``.repo`` — an Android ``repo``-tool workspace root
3. ``.canary-root`` — an explicit ``canary`` workflow root marker

If none is found the filesystem root ``/`` is used as the fallback, which makes IDs
machine-specific (absolute paths differ between machines).

For workflows that are **not** under version control, create a ``.canary-root`` marker file at the
root of the workflow tree:

.. code-block:: console

   touch /path/to/my/workflow/.canary-root

This is a zero-byte file whose only purpose is to serve as the anchor.  It can be committed to
whatever version control system is in use, or simply left in place on the shared filesystem.
