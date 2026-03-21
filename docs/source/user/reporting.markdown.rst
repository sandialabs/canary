.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-markdown:

Multi-page markdown report
==========================

A multi-page `markdown <https://en.wikipedia.org/wiki/Markdown>`_ report of a test session can be generated after the session has completed:

.. command-output:: canary run ./basic
    :cwd: /examples
    :nocache:
    :setup: rm -rf .canary TestResults
    :ellipsis: 0

.. command-output:: canary report markdown create
    :nocache:
    :cwd: /examples

.. command-output:: cat TestResults/canary-report.md
    :nocache:
    :cwd: /examples
