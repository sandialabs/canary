.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.location:

canary location
===============

Print locations of test files and directories

.. code-block:: console

   usage: canary location [-h] [-i | -l | -x | -s] testspec
   
   Print locations of test files and directories
   
   positional arguments:
     testspec    Test name or test id
   
   options:
     -i          Show the location of the test's input file
     -l          Show the location of the test's log file
     -x          Show the location of the test's working directory
     -s          Show the location of the test's source directory
     -h, --help  Show this help message and exit.
   
   If no options are give, -x is assumed.
