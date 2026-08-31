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
   :before_script: [copy-examples]
   :script: ["canary run ./status"]
   :cwd: /examples
   :returncode: [14]


Rerun all failed tests
~~~~~~~~~~~~~~~~~~~~~~

.. doc-run::
   :before_script: [copy-examples, "canary run ./status || true"]
   :script: ["canary run -k 'not success'"]
   :cwd: /examples
   :returncode: [14]
   :shell:

Rerun only the diffed tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. doc-run::
   :before_script: [copy-examples, "canary run ./status || true"]
   :script: ["canary run -k diff"]
   :cwd: /examples
   :returncode: [2]
   :shell:

Rerun tests inside the view
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Optionally, a subdirectory of the workspace view argument can be passed to ``canary run``, causing ``canary`` to rerun only those tests that are in ``PATH`` and its children:

.. doc-run::
   :before_script: [copy-examples, "canary run ./status || true"]
   :script: ["canary run $(canary location pass)"]
   :cwd: /examples
   :returncode: [0]
   :shell:
