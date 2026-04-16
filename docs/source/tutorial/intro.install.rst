.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Installing canary
=================

Create and activate a virtual environment, then install ``canary-wm`` from PyPI:

.. code-block:: console

    python3 -m venv venv
    source venv/bin/activate
    python3 -m pip install canary-wm

Verify the installation
-----------------------

Confirm the command-line interface is available:

.. code-block:: console

    canary --help

(Optional) avoid reinstalling example dependencies
--------------------------------------------------

If you plan to run the tutorial examples, consider installing in a clean environment to avoid
version conflicts with other Python packages.
