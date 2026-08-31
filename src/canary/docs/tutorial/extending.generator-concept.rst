.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-extending-generator-concept:

Job generators
==============

A **job generator** is responsible for:

1. deciding whether it recognizes a file (a *match* step); and
2. generating one or more :class:`~_canary.job.Job` objects from that file.

In other words: ``canary`` discovers files, but plugins decide which of those files become runnable
jobs.

At a minimum, a generator typically provides:

* a ``matches(path)`` method to identify supported files; and
* a method that returns a list of jobs (in this example, ``lock()``).

Each generated :class:`~_canary.job.Job` controls execution details such as:

* the test *family* (name);
* keywords/labels;
* parameters (used for naming, filtering, and resource requirements);
* the test working directory and setup; and
* the launcher/executable used to run the test.
