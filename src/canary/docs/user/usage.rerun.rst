.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-rerun:

Rerunning tests
===============

By default, only tests that had previously not run will be rerun, unless the test is explicitly requested via keyowrd or other :ref:`filters <usage-filter>`.

Filter tests based on previous status
-------------------------------------

In rerun mode, the previous test status is included implicitly as a test keyword which allows :ref:`filtering <usage-filter>` based on previous statuses.

Examples
--------

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./status", "returns": 14, "cwd": "examples"}]


Rerun all failed tests
~~~~~~~~~~~~~~~~~~~~~~

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary run ./status || true", "cwd": "examples"}]
   :script: [{"args": "canary run -k 'not success'", "returns": 14, "cwd": "examples"}]

Rerun only the diffed tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary run ./status || true", "cwd": "examples"}]
   :script: [{"args": "canary run -k diff", "returns": 2, "cwd": "examples"}]

Rerun tests inside the view
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Optionally, a subdirectory of the workspace view argument can be passed to ``canary run``, causing ``canary`` to rerun only those tests that are in ``PATH`` and its children:

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}, {"args": "canary run ./status || true", "cwd": "examples"}]
   :script: [{"args": "canary run $(canary location pass)", "cwd": "examples"}]

Rerun strategies with ``--only``
---------------------------------

When you run in an existing workspace, ``canary`` re-runs a subset of the
previously known jobs.  The ``--only`` option chooses which subset:

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Strategy
     - Behaviour
   * - ``not_pass`` *(default)*
     - Run jobs whose latest result did not pass (failed, diffed, timed out,
       aborted, or never run)
   * - ``all``
     - Run all selected jobs, even if they already passed
   * - ``failed``
     - Run only jobs whose latest result failed
   * - ``not_run``
     - Run only jobs that have never been executed
   * - ``changed``
     - Run only jobs whose source file changed since their last run (a job that
       has never run counts as changed)

When you re-run specific tests **by ID or by view path**, ``--only`` defaults to
``all`` instead of ``not_pass`` — asking for a specific test by name means you
want it to run even if it already passed.  Pass ``--only`` explicitly to
override this (for example, ``canary run --only failed <id>``); ``canary`` logs
a note when it applies the ``all`` default so the choice is visible.

Examples:

.. code-block:: console

   canary run --only all .
   canary run --only failed .
   canary run --only not_run .
   canary run --only changed .
