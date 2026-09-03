.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-markdown:

Multi-page markdown report
==========================

A multi-page `markdown <https://en.wikipedia.org/wiki/Markdown>`_ report of a test session can be
generated after the session has completed:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./basic", "ellipsis": 0, "cwd": "examples"}, {"args": "canary report markdown create", "cwd": "examples"}, {"args": "cat MARKDOWN/index.md", "cwd": "examples"}]

Report structure
----------------

The report is written to a ``MARKDOWN/`` directory (symlinked as ``Canary.md`` in the workspace
parent).  It contains one file per result group plus a per-job detail page for every test:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - File
     - Contents
   * - ``index.md``
     - Summary table with site, project name, and per-group counts linked to group files
   * - ``Total.md``
     - All tests sorted by duration (Test, ID, Duration, Status)
   * - ``Pass.md``
     - Tests with a passing outcome (``success``, ``xfail``, ``xdiff``)
   * - ``Fail.md``
     - Tests that failed
   * - ``Diff.md``
     - Tests that diffed
   * - ``Timeout.md``
     - Tests that exceeded their timeout
   * - ``NotRun.md``
     - Tests that were not run (``skipped``, ``blocked``, no result)
   * - ``Cancelled.md``
     - Tests that were cancelled or interrupted
   * - ``Invalid.md``
     - Tests with an invalid result
   * - ``<job_id>.md``
     - Per-test detail: status, exit code, ID, location, duration, reason, and console output

