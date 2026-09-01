.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-markdown:

Multi-page markdown report
==========================

A multi-page `markdown <https://en.wikipedia.org/wiki/Markdown>`_ report of a test session can be generated after the session has completed:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./basic", "ellipsis": 0, "cwd": "examples"}, {"args": "canary report markdown create", "cwd": "examples"}, {"args": "cat MARKDOWN/index.md", "cwd": "examples"}]
