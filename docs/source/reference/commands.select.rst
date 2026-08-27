.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.select:

canary select
=============

Create tagged selection of tests

.. code-block:: console

   usage: canary select [-r root] [-d] [-m oldtag] [-f tag] [-k expression] [--owner OWNERS] [-p expression]
                        [--regex regex] [-h]
                        tag
   
   Create tagged selection of tests
   
   options:
     -h, --help            Show this help message and exit.
   
   test spec selection:
     -r, --from-root root  Restrict selection to tests whose source files are located under root
     -d, --delete          Delete tag
     -m, --move oldtag     Move/rename oldtag to tag
     -f, --from tag        Create selection from tag
     -k expression         Restrict selection to tests matching expression. For example: `-k 'key1 and not key2'`. The keyword ``:all:`` matches all tests
     --owner OWNERS        Restrict selection to tests owned by 'owner'
     -p expression         Restrict selection to tests matching the paramter expression. For example: '-p cpus=8' or '-p cpus<8'
     --regex regex         Restrict selection to tests containing the regular expression regex in at least 1 of its file assets. regex is a python regular expression, see
                           https://docs.python.org/3/library/re.html
     tag                   Name this selection 'tag'
