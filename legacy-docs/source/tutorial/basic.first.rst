.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-basic-first:

A first test
============

This section walks through a minimal ``.pyt`` test: what it looks like, how to run it, and where
to find results.

The test file
-------------

Consider the test file ``first.pyt``:

.. literalinclude:: /examples/basic/first/first.pyt
   :language: python

This example also introduces a *directive*: :func:`canary.directives.keywords`. Directives are how
a test file communicates metadata and configuration back to ``canary`` during test discovery and
generation. The ``keywords`` directive assigns labels to a test, which can later be used for
filtering (for example, selecting a subset of tests to run).

.. note::

   Files ending in ``.pyt`` are Python scripts that use ``canary`` directives. The remainder of
   this tutorial uses ``.pyt`` examples unless noted otherwise.

Running the test
----------------

To run the test, navigate to ``examples/basic/first`` and execute:

.. command-output:: canary run .
   :cwd: /examples/basic/first
   :nocache:
   :setup: rm -rf .canary TestResults

A test is considered successful if it exits with return code ``0``. See :ref:`basics-status` for
more details on statuses and failure modes.

Inspecting the results
----------------------

Tests run inside a per-session *workspace* (stored under ``.canary``). After execution finishes,
``canary`` writes a user-facing view of the session under ``TestResults``. The session tree mirrors
the source tree used to generate the session:

.. command-output:: canary tree examples/basic/first/TestResults
   :nocache:

To see status information for the session, run :ref:`canary status <canary-status>` from within
the session directory:

.. command-output:: canary status
   :nocache:
   :cwd: /examples/basic/first

By default, ``canary status`` prints details only for non-passing tests. To show all tests,
including passing ones, use ``-rA``:

.. command-output:: canary status -rA
   :nocache:
   :cwd: /examples/basic/first


.. program-output:: rm -rf .canary TestResults
   :silent:
   :nocache:
   :cwd: /examples/basic/first
