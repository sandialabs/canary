.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-html:

Multi-page HTML report
======================

A multi-page HTML report of a test session can be generated after the session has completed:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./basic", "cwd": "examples", "ellipsis": 0}, {"args": "canary report html", "cwd": "examples"}, {"args": "cat HTML/index.html", "cwd": "examples"}]
