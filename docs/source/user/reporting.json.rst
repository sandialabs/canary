.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-json:

JSON report
===========

A JSON report of a test session can be generated after the session has completed:

.. command-output:: canary run -d TestResults.JSON ./basic
    :nocache:
    :cwd: /examples
    :ellipsis: 0
    :setup: rm -rf TestResults.JSON

.. command-output:: canary -C TestResults.JSON report json create
    :nocache:
    :cwd: /examples

.. command-output:: cat TestResults.JSON/canary.json
    :nocache:
    :cwd: /examples
