.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _reporting-markdown:

Multi-page markdown report
==========================

A multi-page `markdown <https://en.wikipedia.org/wiki/Markdown>`_ report of a test session can be generated after the session has completed:

.. doc-run::
   :before_script: [copy-examples]
   :script: [canary run ./basic, canary report markdown create, cat MARKDOWN/index.md]
   :cwd: /examples
   :ellipsis: [0, null, null]
