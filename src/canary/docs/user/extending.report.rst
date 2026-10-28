.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-report:

User defined reports
====================

``canary`` can write output in a number of formats, including ``JSON``, ``HTML``, and ``Markdown``. See :ref:`canary-report` for built-in formats. User-defined report formats can be created by returning an instance of ``canary.CanaryReporter`` from the :func:`~_canary.plugins.hookspec.canary_reporter` plugin hook. For example, the following writes a custom plain-text report.

.. code-block:: python

   import os

   import canary

   @canary.hookimpl
   def canary_reporter():
       return TxtReporter()


   class TxtReporter(canary.CanaryReporter):
       type = "txt"
       description = "Create a plain text report"

       def create(self, output: str | None = None) -> None:
           output = output or "canary-report.txt"
           workspace = canary.Workspace.load()
           with open(output, "w") as fh:
               for job in workspace.load_jobs():
                   fh.write("====\n")
                   fh.write(f"Name: {job.spec.name}\n")
                   fh.write(f"Start: {job.timekeeper.started_on}\n")
                   fh.write(f"Finish: {job.timekeeper.finished_on}\n")
                   fh.write(f"Status: {job.status.outcome.name}\n")

.. code-block:: console

   $ canary report txt -h
   usage: canary report txt [-h]  ...

   positional arguments:

      create    Create plain text report

   options:
      -h, --help  show this help message and exit
   $ canary report txt create -h
   usage: canary report txt create [-h] [-o O]

   options:
      -h, --help  show this help message and exit
      -o O        Output file name [default: ./output.txt]
