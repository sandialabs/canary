.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-workspace:

.. command-output:: rm -rf .canary TestResults
   :cwd: /examples
   :silent:

Canary basics: the Canary workspace
===================================

The Canary workspace is a folder in which all inputs, intermediate files, and outputs are contained.

Creating the workspace
----------------------

At the command line, type:

.. command-output:: canary init .
   :cwd: /examples

This creates a new folder named ``.canary`` that contains all of the necessary workspace files.

The workspace can be inspected via ``canary info``:

.. command-output:: canary info
   :cwd: /examples

At this point, the workspace is empty.  Tests are added to the workspace by creating a "selection":

.. command-output:: canary selection create -h
   :cwd: /examples

Let's add the basic examples to the workspace and tag the selection "basic":

.. command-output:: canary selection create -r ./basic basic
   :cwd: /examples

Running ``canary info`` now reports the addition of this tag:

.. command-output:: canary info
   :cwd: /examples

Running tests
-------------

A tagged selection is run by ``canary run TAGNAME``.  To run the previously tagged "basic" selection, execute:


.. command-output:: canary run basic
   :cwd: /examples


Status
------

To get the status of tests in the workspace, type:

.. command-output:: canary status -rA
   :cwd: /examples

``canary status`` tells you the ID and name of the test, which session that test was run in, exit code, duration, and status.

The workspace view
------------------

On completion of ``canary run``, a "view" of the latest test results is created in a folder named ``TestResults``.  The view is a directory structure mirroring the test source tree.  After running the basic tag, the view contains entries for the ``basic/first`` and ``basic/second`` tests:

.. command-output:: ls -F TestResults
   :cwd: /examples


.. command-output:: rm -rf .canary TestResults
   :cwd: /examples
   :silent:
