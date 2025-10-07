.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-junit:

Generating JUnit reports
========================

A junit report of a test session can be generated after the session has completed:

.. command-output:: canary run -d TestResults.junit ./basic
    :cwd: /examples
    :nocache:
    :setup: rm -rf TestResults.junit
    :ellipsis: 0

.. command-output:: canary -C TestResults.junit report junit create
    :nocache:
    :cwd: /examples

.. command-output:: cat TestResults.junit/junit.xml
    :nocache:
    :cwd: /examples
