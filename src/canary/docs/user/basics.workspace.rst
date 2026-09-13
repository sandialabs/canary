.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-workspace:

Canary basics: the Canary workspace
===================================

The Canary workspace is a folder in which all inputs, intermediate files, and outputs are contained.

Creating the workspace
----------------------

At the command line, type:

.. doc-run::
   :script: [{"args": "canary init ."}]

This creates a new folder named ``.canary`` that contains all of the necessary workspace files.

.. note::

   If your workflow is not under version control, place a ``.canary-root`` marker file at the root
   of your workflow tree:

   .. code-block:: console

      touch .canary-root

   ``canary`` walks up the directory tree looking for ``.git``, ``.repo``, or ``.canary-root`` to
   anchor the repo-relative path component of each job's stable ID.  Without one of these anchors
   the filesystem root ``/`` is used, making job IDs machine-specific.  A ``.canary-root`` marker
   is sufficient to ensure IDs are consistent across machines for the same workflow tree.

The workspace can be inspected via ``canary info``:

.. doc-run::
   :before_script: [{"args": "canary init ."}]
   :script: [{"args": "canary info"}]

At this point, the workspace is empty.  Tests are added to the workspace by collecting test case generators and creating a "selection":

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary init .", "cwd": "examples"}]
   :script: [{"args": "canary collect -r ./basic", "cwd": "examples"}, {"args": "canary select basic", "cwd": "examples"}]

Running ``canary info`` now reports the addition of this tag:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary init .", "cwd": "examples"}, {"args": "canary collect -r ./basic", "cwd": "examples"}, {"args": "canary select basic", "cwd": "examples"}]
   :script: [{"args": "canary info", "cwd": "examples"}]

Running tests
-------------

A tagged selection is run by ``canary run TAGNAME``.  To run the previously tagged "basic" selection, execute:


.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary init .", "cwd": "examples"}, {"args": "canary collect -r ./basic", "cwd": "examples"}, {"args": "canary select basic", "cwd": "examples"}]
   :script: [{"args": "canary run basic", "cwd": "examples"}]


Status
------

To get the status of tests in the workspace, type:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary run ./basic", "cwd": "examples"}]
   :script: [{"args": "canary status -rA", "cwd": "examples"}]

``canary status`` tells you the ID and name of the test, which session that test was run in, exit code, duration, and status.

The workspace view
------------------

On completion of ``canary run``, a "view" of the latest test results is created in a folder named ``TestResults``.  The view is a directory structure mirroring the test source tree.  After running the basic tag, the view contains entries for the ``basic/first`` and ``basic/second`` tests:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary run ./basic", "cwd": "examples"}]
   :script: [{"args": "ls -F TestResults", "cwd": "examples"}]

Workspace directory structure
------------------------------

The ``.canary/`` directory has the following internal layout:

.. code-block:: text

   .canary/
   ├── WORKSPACE.TAG          # Workspace anchor (do not edit)
   ├── VERSION                # Workspace format version (do not edit)
   ├── config.yaml            # Workspace-specific configuration (safe to edit)
   ├── workspace.sqlite3      # Main database (do not edit manually)
   ├── refs/
   │   └── latest             # Relative symlink to most recent session
   ├── sessions/              # One subdirectory per execution run
   │   └── {session_name}/
   │       ├── session.lock   # Session manifest
   │       └── {job_dirs}/    # Per-job execution directories
   ├── cache/
   │   ├── jobs/              # Job timing history (for adaptive scheduling)
   │   └── view               # Reference to latest TestResults view
   ├── tmp/                   # Temporary files (managed automatically)
   ├── logs/                  # Canary diagnostic logs
   └── reports/               # Generated reports

Key files and directories:

``WORKSPACE.TAG``
  Marks this directory as a ``canary`` workspace.  Enables workspace discovery
  when traversing directory trees.  Do not edit.

``workspace.sqlite3``
  The SQLite database storing all persistent ``canary`` data: job specifications
  (``specs`` table), execution results (``results`` table), tagged selections
  (``selections`` table), dependency relationships (``spec_deps`` table), and
  source-file/view mappings (``specs_meta`` table).  Use ``canary`` commands to
  query or modify this data — do not edit the file directly.

``refs/latest``
  A relative path reference pointing to the most recently completed session.
  Updated automatically after each run.

``cache/jobs/``
  Per-job timing history files used for adaptive scheduling and runtime estimation.
  Organized by ID prefix for efficient lookup.

``config.yaml``
  Workspace-specific configuration that overrides global settings.  Safe to edit
  and commit to version control.  See :ref:`configuration-file`.

What not to edit manually
~~~~~~~~~~~~~~~~~~~~~~~~~

The following should only be modified through ``canary`` commands:

- ``WORKSPACE.TAG``, ``VERSION`` — workspace metadata
- ``workspace.sqlite3`` — use ``canary status``, ``canary query``, etc.
- ``refs/latest`` — updated automatically by ``canary run``
- ``session.lock``, ``testcase.lock`` — written by the execution engine
- ``cache/`` — managed automatically for scheduling purposes
- ``tmp/`` — transient files, cleaned automatically

Workspace best practices
~~~~~~~~~~~~~~~~~~~~~~~~

1. Create one workspace per project root
2. Commit ``.canary/config.yaml`` to version control for team-wide settings
3. Use ``canary gc`` periodically to remove old session directories
4. Back up ``workspace.sqlite3`` if historical result data is important
