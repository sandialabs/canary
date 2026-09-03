.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _configuration-sections:

Configuration settings
======================

General configuration settings
------------------------------

.. code-block:: yaml

  debug: false  # (bool)
  log_level: "INFO"  # (str)

plugins
-------

Plugins to load

.. code-block:: yaml

   plugins: []  # (list of str)

timeout
-------

Set test timeouts based on :ref:`keywords<directive-keywords>`.  The ``fast`` and ``long`` timeouts are applied to tests having ``fast`` or ``long`` :ref:`keywords<directive-keywords>`, otherwise the ``default`` timeout is applied.

.. code-block:: yaml

  timeout:
    fast: T  # (number or str) default: 30s
    long: T  # (number or str) default: 10m
    default: T  # (number or str) default: 5m

.. note::

  Users can specify custom timeouts associated with keywords by adding them to the ``test:timeout`` configuration. For instance, to set a timeout of 1 second for tests labeled with the ``unit_test`` keyword, simply define the ``test:timeout:unit_test`` setting as follows:

  .. code-block:: yaml

     timeout:
       unit_test: 1s

  The same can be accomplished on the command line: ``canary -c test:timeout:unit_test:1s ...``.

environment
-----------

Modify environment variables.

.. code-block:: yaml

   environment:
     set:
       var: value # (str) environment variables to set for the test session
     unset:
     - var # (str) environment variables to unset for the test session
     prepend-path:
       PATHNAME: value # (str) prepend value to path variable PATHNAME
     append-path:
       PATHNAME: value # (str) append value to path variable PATHNAME

workspace
---------

.. code-block:: yaml

   workspace:
     view: TestResults


run
---

.. code-block:: yaml

   run:
     default_tag: ':all:'
     timeout:
       str: T
     cache:
       dir: null  # (str or null) explicit path to the job result cache directory

The ``run.cache.dir`` setting specifies an explicit directory for the per-job result cache (used for
runtime history and staleness detection).  When set, it takes precedence over automatic workspace
discovery.  The full resolution order is:

1. ``CANARY_CACHE_DIR`` environment variable
2. ``run.cache.dir`` configuration key
3. Walk up the directory tree from the workspace for a ``WORKSPACE.TAG`` sentinel, then use
   ``<dir>/cache``
4. Fall back to ``.canary/cache`` relative to the current directory

This is primarily useful when multiple workspaces or HPC batch jobs share a single cache directory
on a network filesystem.  See :ref:`basics-runtimes` for details on cache locking and concurrent
access.
