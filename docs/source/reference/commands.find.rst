.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.find:

canary find
===========

Search paths for test files

.. code-block:: console

   usage: canary find [--paths | --files | -g | -l | --keywords] [-f file] [-r PATH] [-o option] [-k expression]
                      [--owner OWNERS] [-p expression] [--regex regex] [--workers N] [--timeout type=T]
                      [--no-incremental] [-h] [--ctest-config cfg] [--recurse-ctest] [--show-excluded-tests]
   
   Search paths for test files
   
   options:
     --paths               Print file paths, grouped by root
     --files               Print file paths
     -g, --graph           Print DAG of test specs
     -l, --lock            Dump test specs to lock file
     --keywords            Print keywords by root
     -f file               Read test paths from a json or yaml file. See 'canary help --pathfile' for help on the file schema
     -r PATH               Recursively search PATH for test generators
     -h, --help            Show this help message and exit.
   
   test spec generation:
     -o option             Turn option(s) on, such as '-o dbg' or '-o intel'
   
   test spec selection:
     -k expression         Restrict selection to tests matching expression. For example: `-k 'key1 and not key2'`. The keyword ``:all:`` matches all tests
     --owner OWNERS        Restrict selection to tests owned by 'owner'
     -p expression         Restrict selection to tests matching the paramter expression. For example: '-p cpus=8' or '-p cpus<8'
     --regex regex         Restrict selection to tests containing the regular expression regex in at least 1 of its file assets. regex is a python regular expression, see
                           https://docs.python.org/3/library/re.html
   
   resource control:
     --workers N           Execute the test session asynchronously using a pool of at most N workers
     --timeout type=T      Set the timeout for **type** (accepts Go's duration format, eg, 40s, 1h20m, 2h, 4h30m30s).
                           • type=**session**, the timeout T is applied to the entire test session.
                           • type=**multiplier**, the multiplier T is applied to each test's timeout.
                           • type=**all**, the timeout T is applied to all jobs.
                           Otherwise, a timeout of T is applied to tests having keyword **type**. Eg, **--timeout fast=2** would apply a timeout of 2 seconds to all tests having the 'fast' keyword;
                           common types are fast, long, default, and ctest.
     --no-incremental      Don't use the .canary_cache to infer job runtimes
   
   ctest options:
     --ctest-config cfg    Choose configuration to test
     --recurse-ctest       Recurse CMake binary directory for test files. CTest tests can be detected from the root CTestTestfile.cmake, so this is option is not necessary unless there is a mix of
                           CTests and other test types in the binary directory
   
   console reporting:
     --show-excluded-tests
                           Show names of tests that are excluded from the test session False
   
   See canary help --pathspec for help on the path specification
