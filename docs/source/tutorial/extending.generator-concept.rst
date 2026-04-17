.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-extending-generator-concept:

Testcase generators
===================

A **testcase generator** is responsible for:

1. deciding whether it recognizes a file (a *match* step); and
2. generating one or more :class:`~_canary.test.case.TestCase` objects from that file.

In other words: ``canary`` discovers files, but plugins decide which of those files become runnable
test cases.

At a minimum, a generator typically provides:

* a ``matches(path)`` method to identify supported files; and
* a method that returns a list of test cases (in this example, ``lock()``).

Each generated :class:`~_canary.test.case.TestCase` controls execution details such as:

* the test *family* (name);
* keywords/labels;
* parameters (used for naming, filtering, and resource requirements);
* the test working directory and setup; and
* the launcher/executable used to run the test.
