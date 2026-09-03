.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _intro-install:

Installing canary
=================


.. note::

   ``canary`` requires Python 3.10+

Basic installation
------------------

1. Create and activate a python virtual environment.

   .. code-block:: console

      python3 -m venv venv
      source venv/bin/activate

2. Install via ``pip`` into the virtual environment

   .. code-block:: console

      python3 -m pip install "canary-wm git+ssh://git@github.com/sandialabs/canary"


Editable installation
---------------------

An "editable installation" installs package dependencies, metadata, and wrappers for console scripts, but not the package itself.  Instead, custom import hooks are generated to import your package from its source directory.  By default, the editable installation clones the source into ``$VIRTUAL_ENV/src``.

1. Create and activate a python virtual environment.

   .. code-block:: console

      python3 -m venv venv
      source venv/bin/activate

2. Install via ``pip`` into the virtual environment with the ``-e`` flag

   .. code-block:: console

      python3 -m pip install -e git+ssh://git@github.com/sandialabs/canary#egg=canary

Alternatively, the package can be installed from a source checkout:

1. Create and activate a python virtual environment.

   .. code-block:: console

      python3 -m venv venv
      source venv/bin/activate

2. Clone the source code:

   .. code-block:: console

      git clone git@github.com:sandialabs/canary

3. Install via ``pip`` into the virtual environment with the ``-e`` flag

   .. code-block:: console

      cd canary
      python3 -m pip install -e .

Plugin packages
---------------

The ``canary-wm`` package installs the ``canary`` core.  Additional capabilities are provided by
separately installable plugin packages:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Package
     - Provides
   * - ``canary-pyt``
     - ``.pyt`` Python job-definition generator (the primary test format)
   * - ``canary-hpc``
     - HPC batch scheduler integration (Slurm, PBS, Flux, shell)
   * - ``canary-vvtest``
     - ``.vvt`` vvtest-format test file generator
   * - ``canary-cdash``
     - CDash XML report generation and upload
   * - ``canary-gitlab``
     - GitLab merge-request reporting

Install any subset with:

.. code-block:: console

   python3 -m pip install canary-pyt canary-hpc canary-vvtest

