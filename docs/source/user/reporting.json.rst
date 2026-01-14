.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-json:

JSON report
===========

A JSON report of a test session can be generated after the session has completed:

.. command-output:: canary run ./basic
    :nocache:
    :cwd: /examples
    :ellipsis: 0
    :setup: rm -rf .canary TestResults

.. command-output:: canary report json create
    :nocache:
    :cwd: /examples

.. command-output:: cat canary.json
    :nocache:
    :cwd: /examples
