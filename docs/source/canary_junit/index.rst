.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

canary_junit
============

The `canary_junit <https://github.com/sandialabs/canary/tree/main/src/canary_junit>`_ plugin extends `canary <https://github.com/sandialabs/canary>`_ to generate `JUnit XML files <https://www.ibm.com/docs/en/developer-for-zos/16.0?topic=formats-junit-xml-format>`_ for a completed test session.  The JUnit XML report format is a standardized structure for representing the results of unit tests, commonly used in continuous integration and continuous deployment (CI/CD) pipelines. This format, which is based on XML (Extensible Markup Language), allows for the systematic recording of test outcomes, including details such as the number of tests run, passed, failed, and skipped, as well as specific error messages and stack traces for failed tests.

Installation
------------

At this time, ``canary_junit`` is installed with ``canary``::

   pip install canary-wm

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   spec
   usage
