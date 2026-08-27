.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.log:

canary log
==========

Show the session or a job's log file

.. code-block:: console

   usage: canary log [-h] [-e | -l | -f PATH] [--raw] [testspec]
   
   Show the session or a job's log file
   
   positional arguments:
     testspec         Test name or TEST_ID. If not given, the session log will be shown
   
   options:
     -e, --error      Display test stderr if it exists
     -l, --lock       Display test lockfile if it exists; equivalent to -f testcase.lock
     -f, --file PATH  Display PATH from the test's workspace
     --raw            Show raw log file contents (applicable only to the session log file)
     -h, --help       Show this help message and exit.
