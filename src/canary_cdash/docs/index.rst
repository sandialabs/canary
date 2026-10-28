.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

CDash Reporting
===============

The ``canary_cdash`` extension provides CDash reporting functionality for Canary. It enables generating CDash-compatible XML reports from Canary workspace results and uploading them to CDash servers.

Use ``canary_cdash`` when you need to publish completed Canary results to a
CDash dashboard or generate CDash-oriented summaries and artifacts.

Prerequisites
-------------

- A completed Canary workspace or session.
- A reachable CDash server for upload workflows.

Quick Start
-----------

Generate a CDash report from the current workspace:

.. code-block:: console

   canary report cdash create --build MyBuild --site MySite

.. note::

   ``canary_cdash`` is a **built-in** canary extension, included in the
   ``canary-wm`` package.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   overview
   reporter-plugin
   xml-generation
   customization
   uploading
   metadata
   labels-and-subprojects
   artifacts
   summaries
   gitlab-issues
   limitations

See Also
--------

- :doc:`/user/basics.concepts`: Canary core concepts
- :doc:`/user/commands/report`: Canary report command reference
- :doc:`/dev/flow`: Canary execution flow
- :doc:`/user/usage.cmake.cdash`: User guide for CDash reporting
