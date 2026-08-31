.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-json:

JSON report
===========

A JSON report of a test session can be generated after the session has completed:

.. doc-run::
   :before_script: [copy-examples]
   :script: ["canary run ./basic", "canary report json create", "cat canary.json"]
   :cwd: /examples
   :ellipsis: [0, null, null]
