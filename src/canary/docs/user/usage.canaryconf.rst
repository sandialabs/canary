.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _user-canaryconf:

Directory-scoped setup and teardown
=====================================

``canaryconf.py`` is a sentinel file you can place in any directory of your
test tree.  When ``canary`` finds one, it automatically runs the
``canary_setup`` and/or ``canary_teardown`` functions defined in that file
before and after every test whose path falls at or below that directory.

This is the preferred way to handle shared one-time setup — such as building
a fixture binary, staging data files, or acquiring a resource — that is needed
by every test in a sub-tree, without modifying individual test files.

Quick start
-----------

Create a ``canaryconf.py`` next to the tests that need it:

.. code-block:: python

   # tests/integration/canaryconf.py

   def canary_setup(ctx):
       """Run before every test in tests/integration/ and its subdirectories."""
       import subprocess
       subprocess.run(["make", "-C", str(ctx.file_root), "fixture"], check=True)

   def canary_teardown(ctx):
       """Run after every test in tests/integration/, even on failure."""
       import shutil
       shutil.rmtree(ctx.exec_dir / "fixture-tmp", ignore_errors=True)

Both functions are optional.  A ``canaryconf.py`` that defines only
``canary_setup`` or only ``canary_teardown`` is valid.

How it works
------------

``canaryconf.py`` files are discovered automatically during the generation
phase; you do not need to register them or add any directives to your test
files.

When ``canary`` generates the job graph it:

1. Scans each test's directory and all ancestor directories (up to the file
   root) for a ``canaryconf.py``.
2. Parses every ``canaryconf.py`` found with ``ast.parse`` to check which of
   the two well-known functions are defined — **without executing user code**.
3. Creates a synthetic *setup* job and/or *teardown* job for each
   ``canaryconf.py`` file that defines at least one of them.
4. Wires dependency edges so that:

   - Every governed test depends on the setup job with ``when="on_success"``
     (tests are skipped if setup fails).
   - The teardown job depends on every governed test with ``when="always"``
     (teardown runs regardless of individual test outcomes).

The ``ctx`` argument
--------------------

Both ``canary_setup`` and ``canary_teardown`` receive the synthetic job's
:class:`~_canary.testinst.TestInstance` as their sole argument, identical to
what a regular test body receives from ``canary.get_instance()``.  Useful
attributes include:

``ctx.file_root``
    The root directory of the test collection that contains this
    ``canaryconf.py``.

``ctx.exec_dir``
    The working directory for this synthetic job's execution (inside the
    canary workspace).

``ctx.environment``
    The environment mapping for this execution.

.. note::

   Setup and teardown are dispatched *in-process*: canary imports the
   ``canaryconf.py`` file and calls ``canary_setup(ctx)`` or
   ``canary_teardown(ctx)`` directly.  The function runs with the working
   directory set to the session-tree location mirroring the ``canaryconf.py``'s
   governing directory.  There is no ``python canaryconf.py`` subprocess and no
   ``CANARY_CONFTEST_PHASE`` environment variable.

Scope and inheritance
---------------------

A ``canaryconf.py`` in a parent directory automatically governs tests in all
of its subdirectories:

.. code-block:: text

   tests/
     canaryconf.py          ← governs tests/a.pyt, tests/sub/b.pyt, etc.
     a.pyt
     sub/
       b.pyt
       canaryconf.py        ← also governs tests/sub/b.pyt (nested)

When a test falls under multiple ``canaryconf.py`` files (one from a parent
and one in its own directory), it gets dependency edges from **all** of them.
Each ``canaryconf.py`` generates its own independent setup/teardown pair.

Filtering synthetic jobs
------------------------

Every synthetic setup and teardown job carries the keyword
``canary_conftest``.  You can exclude them from ``canary status`` output or
rerun filters:

.. code-block:: console

   canary status -k 'not canary_conftest'
   canary run --only failed -k 'not canary_conftest'

Rerun behaviour
---------------

Synthetic jobs have stable IDs derived from the ``canaryconf.py`` path, so
``--only not_pass`` and ``--only failed`` rerun strategies work correctly:

- A setup job that **passed** in a previous session is skipped on rerun.
- A teardown job re-runs whenever any test it governs is re-run, because the
  ``when="always"`` edges make it unready until those tests finish.

Caveats
-------

- ``canaryconf.py`` itself is **never collected as a test**.  ``canary``'s
  collector skips files with that exact name.
- The two functions are located by name using ``ast.parse``.  If your file
  uses conditional imports or dynamic ``exec`` to define them, they will not
  be found.  Define ``canary_setup`` / ``canary_teardown`` as plain
  top-level ``def`` statements.
- Setup and teardown jobs are executed by the same launcher as regular tests.
  They respect resource requests, timeouts, and environment settings if you
  set them directly on ``ctx`` before returning.
