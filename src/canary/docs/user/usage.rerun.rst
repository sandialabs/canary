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
