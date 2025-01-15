.. _basics-status:

Test statuses
=============

Tests can receive one of the following statuses:

.. hlist::
   :columns: 4

   * :ref:`stat-created`
   * :ref:`stat-pending`
   * :ref:`stat-ready`
   * :ref:`stat-running`
   * :ref:`stat-cancelled`
   * :ref:`stat-skipped`
   * :ref:`stat-diffed`
   * :ref:`stat-failed`
   * :ref:`stat-timeout`
   * :ref:`stat-success`
   * :ref:`stat-xfail`
   * :ref:`stat-xdiff`
   * :ref:`stat-not_run`

.. _stat-created:

created
-------

The test case object has been instantiated.

.. _stat-ready:

ready
-----

The test case is setup and ready to run.

.. _stat-pending:

pending
-------

The test case is waiting for one or more dependencies.

.. _stat-running:

running
-------

The test case is currently running.

.. _stat-cancelled:

cancelled
---------

The test case was cancelled while running (usually by a keyboard interrupt).

.. _stat-skipped:

skipped
-------

The test case was skipped due to a skipped dependency or by exiting with a ``63`` exit code.

.. admonition:: Tip

   Don't explicitly exit with code ``63``.  Instead, exit with ``canary.skip_exit_status`` or raise a ``canary.TestSkipped`` exception.

.. _stat-diffed:

diffed
------

A test diffs if it exits with a ``64`` exit code.

.. admonition:: Tip

   Don't explicitly exit with code ``64``.  Instead, exit with ``canary.diff_exit_status`` or raise a ``canary.TestDiffed`` exception.

.. _stat-failed:

failed
------

A test fails if it exits with any nonzero code not previously defined.

.. admonition:: Tip

   To explicitly mark a test as failed, exit with ``canary.fail_exit_status`` or raise a ``canary.TestFailed`` exception.

.. _stat-timeout:

timeout
-------

The test case exceeded its allowed run time.

.. _stat-success:

success
-------

A test is considered successfully passed if it exits with a ``0`` exit code.

.. _stat-xfail:

xfail
-----

The test case is marked as :ref:`expected to fail<directive-xfail>`

.. _stat-xdiff:

xdiff
-----

The test case is marked as :ref:`expected to diff<directive-xdiff>`

.. _stat-not_run:

not_run
-------

A test case that was expected to run was not run.  Common reasons for being marked ``not_run`` are the test case not being run due to a failed or skipped dependency and the test session being stopped prematurely.
