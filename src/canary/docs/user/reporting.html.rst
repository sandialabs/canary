.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-html:

Multi-page HTML report
======================

A multi-page HTML report of a test session can be generated after the session has completed:

.. doc-run::
   :before_script: [copy-examples]
   :script: ["canary run ./basic", "canary report html", "cat HTML/index.html"]
   :cwd: /examples
   :ellipsis: [0, null, null]
