.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.config:

canary config
=============

Get and set configuration options

.. code-block:: console

   usage: canary config [-h] [--oversubscribe TYPE=N] {show,set} ...
   
   Get and set configuration options
   
   positional arguments:
     {show,set}
     show                  Show current configuration. To show the resource pool, let section=resource_pool
     set                   Add to the current configuration
   
   options:
     -h, --help            Show this help message and exit.
   
   resource control:
     --oversubscribe TYPE=N
                           Apply the multiplier N to the number of slots available per resource instance of
                           type TYPE
