.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.rebaseline:

canary rebaseline
=================

Update baseline files from existing test results

.. code-block:: console

   usage: canary rebaseline [-h] [-k KEYWORD_EXPR] [DIR_OR_JOBID]
   
   Update baseline files from existing test results
   
   positional arguments:
     DIR_OR_JOBID     Directory containing test results or a job id/name. If a directory is given, testcase.lock files
                      are found recursively. [default: current directory]
   
   options:
     -k KEYWORD_EXPR  Restrict rebaseline to jobs matching keyword expression
     -h, --help       Show this help message and exit.
