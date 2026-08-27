.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.collect:

canary collect
==============

Find and generate test cases

.. code-block:: console

   usage: canary collect [-h] [-f file] [-r PATH] [-o option]
   
   Find and generate test cases
   
   options:
     -f file     Read test paths from a json or yaml file. See 'canary help --pathfile' for help
                 on the file schema
     -r PATH     Recursively search PATH for test generators
     -h, --help  Show this help message and exit.
   
   test spec generation:
     -o option   Turn option(s) on, such as '-o dbg' or '-o intel'
