.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.tree:

canary tree
===========

list contents of directories in a tree-like format

.. code-block:: console

   usage: canary tree [-had] [-i I] [--exclude-results] directory
   
   list contents of directories in a tree-like format
   
   positional arguments:
     directory
   
   options:
     -h, --help         show this help message and exit
     -a                 All files are printed. By default, hidden files are not printed
     -d                 List directories only
     -i I               Ignore pattern
     --exclude-results  Exclude test result directories
