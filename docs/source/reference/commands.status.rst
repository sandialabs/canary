.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.status:

canary status
=============

Print information about a test run

.. code-block:: console

   usage: canary status [-h] [--durations [N]] [-o FORMAT_COLS] [-r char] [--sort-by {duration,name}] ...
   
   Print information about a test run
   
   positional arguments:
     specs                 Show status history for these specific specs
   
   options:
     --durations [N]       Show N slowest test durations (N<0 for all) [default: 10]
     -o FORMAT_COLS        Comma separated list of fields to print to the screen [default: ID,Name,Session,Exit Code,Duration,Status,Details]. Choices are:
                           • Name: the job name
                           • FullName: the job full name (name including relative execution path)
                           • Session: the session name the job was last ran in
                           • Exit Code: the job's exit code
                           • Duration: job duration
                           • Status: job exit status
                           • Details: additional details, if any
                           
   
     -r char               Show test summary info as specified by chars: (p)assed, (t)imeout (d)iffed, (f)ailed, (n)ot run, (s)kipped, (a)ll (except passed), (A)ll. [default: dftns]
     --sort-by {duration,name}
                           Sort cases by this field [default: name]
     -h, --help            Show this help message and exit.
