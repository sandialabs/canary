.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.report:

canary report
=============

Create reports from Canary results

.. code-block:: console

   usage: canary report [-h] report-type ...
   
   Create reports from Canary results
   
   positional arguments:
     report-type
     gitlab-mr    GitLab merge request reporter
     cdash        CDash reporter
     markdown     Markdown reporter
     junit        JUnit reporter
     json         JSON reporter
     html         HTML reporter
   
   options:
     -h, --help   Show this help message and exit.
