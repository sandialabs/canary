.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Recording git provenance
========================

``canary_git`` is a Canary plugin extension that records the git commit of each job's file
as a measurement, so a result can be traced back to the source that produced it.

**Extension type**: lifecycle hook (``canary_runteststart``), measurements.

Quick Start
-----------

.. code-block:: console

   canary -p canary_git run ./tests

Or enable it for a project in the Canary configuration file:

.. code-block:: yaml

   plugins: [canary_git]

What is recorded
----------------

When a job's file is tracked by git, the job gets a ``git`` measurement:

.. code-block:: json

   {"git": {"commit": "1cb2f00...", "dirty": false, "root": "/path/to/repo", "path": "tests/foo.pyt"}}

``commit``
   ``HEAD`` of the repository that contains the job file.
``dirty``
   ``true`` if the job file (staged or not) differs from ``HEAD``. Changes to other files
   in the repository do not count.
``root``
   The repository's top-level directory.
``path``
   The job file's path relative to ``root``.

The measurement is stored with the job's other measurements. View it with
``canary query job JOBID``, or in the HTML and CDash reports.

Limitations
-----------

- Nothing is recorded when the job file is not tracked, the repository has no commits,
  ``git`` is not on ``PATH``, or a git command fails or takes longer than 10 seconds. The
  plugin never changes a job's status.
- The hook runs where the job runs. In HPC batches, ``git`` and the source tree must be
  available on the compute node.
- Only the job file is checked. For CMake/CTest jobs the job file is the generated
  ``CTestTestfile.cmake`` in the build tree, which is usually not tracked.

.. note::

   ``canary_git`` is a **built-in** canary extension, included in the ``canary-wm``
   package. It is not enabled by default.
