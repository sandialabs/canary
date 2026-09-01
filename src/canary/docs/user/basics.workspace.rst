.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-workspace:

Canary basics: the Canary workspace
===================================

The Canary workspace is a folder in which all inputs, intermediate files, and outputs are contained.

Creating the workspace
----------------------

At the command line, type:

.. doc-run::
   :script: [{"args": "canary init ."}]

This creates a new folder named ``.canary`` that contains all of the necessary workspace files.

The workspace can be inspected via ``canary info``:

.. doc-run::
   :before_script: [{"args": "canary init ."}]
   :script: [{"args": "canary info"}]

At this point, the workspace is empty.  Tests are added to the workspace by collecting test case generators and creating a "selection":

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary init .", "cwd": "examples"}]
   :script: [{"args": "canary collect -r ./basic", "cwd": "examples"}, {"args": "canary select basic", "cwd": "examples"}]

Running ``canary info`` now reports the addition of this tag:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary init .", "cwd": "examples"}, {"args": "canary collect -r ./basic", "cwd": "examples"}, {"args": "canary select basic", "cwd": "examples"}]
   :script: [{"args": "canary info", "cwd": "examples"}]

Running tests
-------------

A tagged selection is run by ``canary run TAGNAME``.  To run the previously tagged "basic" selection, execute:


.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary init .", "cwd": "examples"}, {"args": "canary collect -r ./basic", "cwd": "examples"}, {"args": "canary select basic", "cwd": "examples"}]
   :script: [{"args": "canary run basic", "cwd": "examples"}]


Status
------

To get the status of tests in the workspace, type:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary run ./basic", "cwd": "examples"}]
   :script: [{"args": "canary status -rA", "cwd": "examples"}]

``canary status`` tells you the ID and name of the test, which session that test was run in, exit code, duration, and status.

The workspace view
------------------

On completion of ``canary run``, a "view" of the latest test results is created in a folder named ``TestResults``.  The view is a directory structure mirroring the test source tree.  After running the basic tag, the view contains entries for the ``basic/first`` and ``basic/second`` tests:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary run ./basic", "cwd": "examples"}]
   :script: [{"args": "ls -F TestResults", "cwd": "examples"}]
