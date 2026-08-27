.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.query:

canary query
============

Query Canary job or session lock files

.. code-block:: console

   usage: canary query [-h] (-j JOBID | -s SESSION) [--terse] [--list] [query]
   
   Query Canary job or session lock files
   
   positional arguments:
     query                 Query expression. If omitted, emit the whole selected JSON object.
   
   options:
     -j, --job JOBID       Query the testcase.lock for JOBID
     -s, --session SESSION
                           Query the session.lock for SESSION
     --terse               Print compact single-line JSON
     --list                List queryable object keys below the selected query point
     -h, --help            Show this help message and exit.
