.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-json:

JSON report
===========

A JSON report of a test session can be generated after the session has completed:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./basic", "ellipsis": 0, "cwd": "examples"}, {"args": "canary report json create", "cwd": "examples"}, {"args": "cat canary.json", "cwd": "examples"}]
