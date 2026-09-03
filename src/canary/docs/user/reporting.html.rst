.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-html:

Multi-page HTML report
======================

A multi-page HTML report of a test session can be generated after the session has completed:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./basic", "cwd": "examples", "ellipsis": 0}, {"args": "canary report html", "cwd": "examples"}, {"args": "cat HTML/index.html", "cwd": "examples"}]

Report structure
----------------

The report is written to an ``HTML/`` directory (symlinked as ``Canary.html`` in the workspace
parent).  It contains a summary index, one page per result group, and per-test detail pages:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - File
     - Contents
   * - ``index.html``
     - Splash summary page with cards linking to each result group and to ``Total.html``
   * - ``Total.html``
     - Sortable table of all tests (Status, Test, ID, Duration)
   * - ``Pass.html``
     - Tests with a passing outcome (``success``, ``xfail``, ``xdiff``)
   * - ``Fail.html``
     - Tests that failed (``failed``, ``error``, ``broken``)
   * - ``Diff.html``
     - Tests that diffed
   * - ``Timeout.html``
     - Tests that exceeded their timeout
   * - ``NotRun.html``
     - Tests that were not run (``skipped``, ``blocked``, no result)
   * - ``Cancelled.html``
     - Tests that were cancelled or interrupted
   * - ``Invalid.html``
     - Tests with an invalid result
   * - ``jobs/<job_id>.html``
     - Per-test detail page: metadata panel, measurements panel, and raw test output
   * - ``files/<job_id>/index.html``
     - File browser for the test's workspace artifacts
   * - ``files/<job_id>/text/<name>.html``
     - Rendered plain-text view of individual artifacts (stdout, testcase.lock, etc.)

