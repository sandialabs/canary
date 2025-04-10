.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _integrations-cdash:

CDash integration
=================

``canary`` can emit `CDash XML files <https://www.python.org>`_ for a completed test session.  The CDash XML report format is a specialized schema designed for the submission and visualization of testing and build results within the CDash (Continuous Dashboard) system, a web-based software testing server. This format leverages XML (Extensible Markup Language) to encapsulate detailed information about the build process, including compilation results, test outcomes, and performance metrics. By standardizing the representation of this data, the CDash XML format enables seamless integration with various build and test systems, facilitating the automated collection, analysis, and display of results on the CDash dashboard. This integration empowers development teams to monitor the health of their software projects in real-time, quickly identify and address issues, and maintain a high level of code quality and reliability throughout the development lifecycle.

See :ref:`usage-cdash` for creating CDash formatted reports.
