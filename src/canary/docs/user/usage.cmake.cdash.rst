.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _integrations-cdash:

CDash integration
=================

``canary`` can emit `CDash XML files <https://www.python.org>`_ for a completed test session.  The
CDash XML report format is a specialized schema designed for the submission and visualization of
testing and build results within the CDash (Continuous Dashboard) system, a web-based software
testing server.

.. _usage-cdash:

Generating CDash XML reports
----------------------------

A CDash report of a test session can be generated after the session has completed:

.. code-block:: console

    $ cd TestResults
    $ canary report cdash create --site=SITE --build=BUILD_NAME

The report can be uploaded to a CDash server via

.. code-block:: console

    $ canary report cdash post --project=PROJECT_NAME --url=URL FILE [FILE ...]

.. note::

   Proxy environment variables (``http_proxy``, ``https_proxy``, ``no_proxy``, etc.) are stripped
   before the upload request so that direct CDash submissions are not accidentally routed through
   an HTTP proxy.

CI integration
--------------

When running in a CI pipeline the upload URL and project name can be supplied through environment
variables instead of command-line flags:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Variable
     - Purpose
   * - ``CDASH_URL``
     - Base URL of the CDash server (e.g. ``https://my-cdash.example.com``)
   * - ``CDASH_PROJECT``
     - CDash project name

GitLab merge-request reporting can link CDash results to an MR by setting additional variables
in the runner environment; see :ref:`canary-gitlab-mr`.

