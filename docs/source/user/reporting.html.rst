.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-html:

Multi-page HTML report
======================

A multi-page HTML report of a test session can be generated after the session has completed:

.. command-output:: canary run -d TestResults.HTML ./basic
    :nocache:
    :cwd: /examples
    :ellipsis: 0
    :setup: rm -rf TestResults.HTML

.. command-output:: canary -C TestResults.HTML report html create
    :nocache:
    :cwd: /examples

.. command-output:: cat TestResults.HTML/canary-report.html
    :nocache:
    :cwd: /examples
