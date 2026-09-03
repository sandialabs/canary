.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-runtimes:

Time resources
==============

Runtime
-------

Test runtimes are written to ``.canary/cache/cases``.  This cache is automatically created when a
session is run and can be ignored from source control.  However, if the timing cache is kept and
updated, the data contained therein can aid in speeding up test runs.

.. _basics-spec-id-stability:

Job ID stability
----------------

Each job has a stable, content-independent ID derived from its family name, repo-relative file path,
and parameters.  The ID is **not** affected by edits to the test file's content (comments, code
formatting, tolerance tweaks), so cached results and runtimes remain valid across such edits.

A separate ``content_hash`` is recorded alongside cached results.  When the ``content_hash``
changes (i.e. the file content was modified) but the ID is unchanged, ``canary`` treats cached
timing data as potentially stale and may re-evaluate it.

.. note::

   To keep IDs stable across machines for workflows **not** under version control, place a
   ``.canary-root`` marker file at the root of the workflow tree.  See
   :ref:`canary-root-anchor` for details.

Timeout
-------

A test case's timeout can be set by the :ref:`timeout <directive-timeout>` directive.  For example,
to set a tests timeout to 5 minutes add the following the test file:

.. code-block:: python

   import canary
   canary.directives.timeout(5 * 60)

If the timeout is not explicitly set, it is set based on the presence of the ``fast`` and ``long``
keywords in a manner similar to `vvtest <https://github.com/sandialabs/vvtest>`_:

* If a test is marked ``fast``, its timeout defaults to 30 seconds.
* If a test is marked ``long``, its timeout defaults to 10 minutes.
* Otherwise the timeout is 5 minutes.

These values are configurable in the ``test:timeout`` :ref:`configuration setting <canary-config>`:

.. code-block:: ini

   test:
     timeout:
       fast = 30s
       long = 10m
       default = 5m

which can also be set from the command line, eg:

.. code-block:: console

   canary -c test:timeout:fast:60s ...

.. note::

   The timeout clock starts from the moment the test **begins executing** (after staging and setup
   are complete), not from when the worker process is launched.  Setup and staging overhead do not
   count against a test's timeout budget.

Timeout multiplier
------------------

You may also want to increase the timeout applied to tests.  Do so by specifying
``--timeout multiplier=X`` option:

.. code-block:: console

   canary run --timeout multiplier=4 ...

In this case, the timeout for each test will be the ``4`` times the test's default timeout.

.. _basics-cache-locking:

Cache concurrency and shared filesystems
-----------------------------------------

The per-job cache file is protected by an advisory file lock and written atomically.  This makes
the cache safe for:

* multiple local workers running jobs concurrently in the same workspace; and
* multiple HPC batch jobs sharing a single cache directory on a network filesystem.

To share a cache across workspaces or batch invocations, point all of them at the same directory
using the ``run.cache.dir`` configuration key or the ``CANARY_CACHE_DIR`` environment variable:

.. code-block:: yaml

   run:
     cache:
       dir: /shared/filesystem/path/to/cache

See :ref:`configuration-sections` for the full resolution order.
