.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-report:

Generating reports
==================

Several report formats are available:

* :ref:`Markdown<usage-md>`
* :ref:`HTML<usage-html>`

.. _usage-md:

Markdown
--------
A markdown report of a test session can be generated after the session has completed:

.. command-output:: canary run -d TestResults.Markdown ./basic
    :cwd: /examples
    :nocache:
    :setup: rm -rf TestResults.Markdown
    :ellipsis: 0

.. command-output:: canary -C TestResults.Markdown report markdown create
    :nocache:
    :cwd: /examples

.. command-output:: cat TestResults.Markdown/canary-report.md
    :nocache:
    :cwd: /examples

.. _usage-html:

HTML
----

A HTML report of a test session can be generated after the session has completed:

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
