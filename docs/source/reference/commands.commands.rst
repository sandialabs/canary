.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.commands:

canary commands
===============

List or generate reference documentation for Canary commands

.. code-block:: console

   usage: canary commands [-h] [--expand] [--style {text,rst}] [--multi-page] [-d DEST] [--wipe] [--dry-run]
   
   List or generate reference documentation for Canary commands
   
   options:
     --expand            Include full argparse help for every command
     --style {text,rst}  Output style [default: text]
     --multi-page        With --style=rst and -d, write one page per command
     -d, --dest DEST     Destination directory. If omitted, output is written to stdout
     --wipe              Remove existing generated command reference files before writing
     --dry-run           Print the files that would be generated without writing them
     -h, --help          Show this help message and exit.
