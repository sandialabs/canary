.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-markdown:

Multi-page markdown report
==========================

A multi-page `markdown <https://en.wikipedia.org/wiki/Markdown>`_ report of a test session can be generated after the session has completed:

.. command-output:: canary run -d TestResults.Markdown ./basic
    :cwd: /examples
    :nocache:
    :setup: rm -rf .canary TestResults.Markdown
    :ellipsis: 0

.. command-output:: canary -C TestResults.Markdown report markdown create
    :nocache:
    :cwd: /examples

.. command-output:: cat TestResults.Markdown/canary-report.md
    :nocache:
    :cwd: /examples
