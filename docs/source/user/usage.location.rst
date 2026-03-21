.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-location:

Finding locations of test assets
================================

It is often useful to know the location a test's execution directory.  The :ref:`canary location<canary-location>` command can display the locations of test assets:


.. command-output:: canary location -h

For example to move to the test execution directory, simply:

.. code-block:: console

    cd $(canary location ID)

where ``ID`` is the test ID that is printed by :ref:`canary status<basics-status>`.
