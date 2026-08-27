.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.selection:

canary selection
================

Create selections of tests to run

.. code-block:: console

   usage: canary selection [-h] [--show-excluded-tests] {create,rm,rename} ...
   
   Create selections of tests to run
   
   positional arguments:
     {create,rm,rename}
   
   options:
     -h, --help            show this help message and exit
   
   console reporting:
     --show-excluded-tests
                           Show names of tests that are excluded from the test session False
