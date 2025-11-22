.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-report:

User defined reports
====================

``canary`` can write output in a number of formats: ``JSON``, ``HTML``, ``Markdown``, among others (see :ref:`canary-report` for additional formats).  User defined report formats can be created by returning an instance of :class:`canary.CanaryReporter` from a :func:`_canary.plugins.hookspec.canary_session_reporter` plugin hook.  For example, the following will write a custom plain text report.

.. code-block:: python

   import os

   import canary

   @canary.hookimpl
   def canary_session_reporter():
       return TxtReporter()


   class TxtReporter(canary.CanaryReporter)
       type = "txt"
       description = "Create a plain text report"

    def create(self, output: str | None = None) -> None:
        """Create a plain text output

        """
        output = output or "canary-report.txt"
        workspace = canary.Workspace.load()
        with open(output, "w") as fh:
            for case in workspace.active_testcases():
                fh.write("====\n")
                fh.write(f"Name: {case.spec.name}\n")
                fh.write(f"Start: {case.timekeeper.started_on}\n")
                fh.write(f"Finish: {case.timekeeper.finished_on}\n")
                fh.write(f"Status: {case.status.name}\n")

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
