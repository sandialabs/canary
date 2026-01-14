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

.. command-output:: canary run ./status
    :cwd: /examples
    :returncode: 14
    :setup: rm -rf .canary TestResults


Rerun all failed tests
~~~~~~~~~~~~~~~~~~~~~~

.. command-output:: canary run -k 'not success'
    :cwd: /examples
    :returncode: 3

Rerun only the diffed tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. command-output:: canary run -k diff
    :cwd: /examples
    :returncode: 3

Rerun tests inside the view
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Optionally, a subdirectory of the workspace view argument can be passed to ``canary run``, causing ``canary`` to rerun only those tests that are in ``PATH`` and its children:

.. command-output:: canary run ./TestResults/pass
    :cwd: /examples
    :returncode: 0
