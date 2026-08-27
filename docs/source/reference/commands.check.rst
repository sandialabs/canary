.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT


.. _commands.check:

canary check
============

Run canary's internal checks

.. code-block:: console

   usage: canary check [-hfcmbtCedv] [--local-packages {yes,no}]
   
   Run canary's internal checks
   
   options:
     -h, --help            show this help message and exit
     -f                    run ruff format (default)
     -c                    run ruff check (default)
     -m                    run mypy (default)
     -b                    run bandit security checks (default)
     -t                    run pytest (default)
     -C                    run coverage
     -e                    run examples test
     -d                    make docs
     -v                    verbose
     --local-packages {yes,no}
                           Add local site-packages to search path when running type checker
