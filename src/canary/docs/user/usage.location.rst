.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-location:

Finding locations of test assets
================================

It is often useful to know the location a test's execution directory.  The :ref:`canary location<canary-location>` command can display the locations of test assets:


.. doc-run::
   :script: [{"args": "canary location -h"}]

For example to move to the test execution directory, simply:

.. code-block:: console

    cd $(canary location ID)

where ``ID`` is the test ID that is printed by :ref:`canary status<basics-status>`.

Batch and JSON forms
--------------------

``canary location`` accepts multiple job IDs and can emit JSON, which is useful for
tools that need execution or log locations for many jobs at once.

It also applies workspace-root remapping when a session was created on a different
host path and is now being inspected from another mount point.
