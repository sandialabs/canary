.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

canary_hpc
==========

The `canary_hpc <https://github.com/sandialabs/canary/tree/main/src/canary_hpc>`_ plugin extends `canary <https://github.com/sandialabs/canary>`_ to run tests through a scheduler on HPC systems using the `hpc-connect <https://github.com/sandialabs/hpc-connect>`_ library.

Installation
------------

At this time, ``canary_hpc`` is installed with ``canary``::

   pip install canary-wm

Features
--------

* **Bin packing**: Tests are packed into "batches" that are submitted to the scheduler asynchronously.
* **Speed**: Tests within a batch are run asynchronously, optimizing resource utilization and speeding up the testing process.

.. toctree::
   :maxdepth: 1
   :caption: Contents:

   run
   resources
