.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-status:

Test statuses
=============

Tests can receive one of the following statuses:

.. hlist::
   :columns: 4

   * :ref:`stat-pending`
   * :ref:`stat-ready`
   * :ref:`stat-running`
   * :ref:`stat-success`
   * :ref:`stat-xfail`
   * :ref:`stat-xdiff`
   * :ref:`stat-failed`
   * :ref:`stat-diffed`
   * :ref:`stat-timeout`
   * :ref:`stat-blocked`
   * :ref:`stat-skipped`
   * :ref:`stat-cancelled`

.. _stat-pending:

pending
-------

The test case is waiting for one or more dependencies.

.. _stat-ready:

ready
-----

The test case is ready to run.

.. _stat-running:

running
-------

The test case is currently running.

.. _stat-cancelled:

cancelled
---------

The test case was cancelled while running (usually by a keyboard interrupt).

.. _stat-skipped:

skipped
-------

The test case was skipped due to a skipped dependency or by exiting with a ``63`` exit code.

.. admonition:: Tip

   Don't explicitly exit with code ``63``.  Instead, exit with ``canary.skip_exit_status`` or raise a ``canary.TestSkipped`` exception.

.. _stat-diffed:

diffed
------

A test diffs if it exits with a ``64`` exit code.

.. admonition:: Tip

   Don't explicitly exit with code ``64``.  Instead, exit with ``canary.diff_exit_status`` or raise a ``canary.TestDiffed`` exception.

.. _stat-failed:

failed
------

A test fails if it exits with any nonzero code not previously defined.

.. admonition:: Tip

   To explicitly mark a test as failed, exit with ``canary.fail_exit_status`` or raise a ``canary.TestFailed`` exception.

.. _stat-timeout:

timeout
-------

The test case exceeded its allowed run time.

.. _stat-success:

success
-------

A test is considered successfully passed if it exits with a ``0`` exit code.

.. _stat-xfail:

xfail
-----

The test case is marked as :ref:`expected to fail<directive-xfail>`

.. _stat-xdiff:

xdiff
-----

The test case is marked as :ref:`expected to diff<directive-xdiff>`

.. _stat-blocked:

blocked
-------

A test case that was expected to run was not run.  Common reasons for being marked ``blocked`` are the test case not being run due to a failed or skipped dependency and the test session being stopped prematurely.

Two-level status model
----------------------

Internally, ``canary`` represents each status using two levels:

- **Category** — high-level outcome: ``PASS``, ``FAIL``, ``CANCEL``, ``SKIP``, or
  ``NONE`` (not yet run)
- **Outcome** — specific result that maps to the user-visible status names above

.. list-table:: Category / Outcome mapping
   :widths: 20 20 60
   :header-rows: 1

   * - Category
     - Outcome
     - Meaning
   * - ``PASS``
     - ``SUCCESS``
     - Job completed with exit code 0
   * - ``PASS``
     - ``XFAIL``
     - Job failed as expected (marked :ref:`xfail <directive-xfail>`)
   * - ``PASS``
     - ``XDIFF``
     - Job diffed as expected (marked :ref:`xdiff <directive-xdiff>`)
   * - ``FAIL``
     - ``FAILED``
     - Job exited with a nonzero code
   * - ``FAIL``
     - ``DIFFED``
     - Job exited with the diff code (64)
   * - ``FAIL``
     - ``TIMEOUT``
     - Job exceeded its allowed run time
   * - ``SKIP``
     - ``SKIPPED``
     - Job was skipped due to conditions or a skipped dependency
   * - ``CANCEL``
     - ``CANCELLED``
     - Job was cancelled by the user or the session
   * - ``NONE``
     - ``BLOCKED``
     - Job could not run due to a failed or unrun dependency

The Category level is what matters for rerun strategies (``--only failed`` targets
``Category=FAIL``, etc.) and for reporting summaries.

Process return codes
--------------------

The specific exit codes that ``canary`` assigns meaning to are:

.. list-table::
   :widths: 15 85
   :header-rows: 1

   * - Exit code
     - Meaning
   * - ``0``
     - Success (``PASS / SUCCESS``)
   * - ``63``
     - Skip (``SKIP / SKIPPED``) — prefer ``canary.skip_exit_status`` or raise
       ``canary.TestSkipped``
   * - ``64``
     - Diff (``FAIL / DIFFED``) — prefer ``canary.diff_exit_status`` or raise
       ``canary.TestDiffed``
   * - other non-zero
     - Failure (``FAIL / FAILED``)
