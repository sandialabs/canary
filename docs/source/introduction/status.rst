.. _introduction-status:

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

The test case was cancelled (usually by a keyboard interrupt).

.. _stat-skipped:

skipped
-------

The test case was skipped due to a failed dependency or skipped at runtime by exiting a ``63`` exit code.

.. admonition:: Tip

   Don't explicitly exit with code ``63``.  Instead, exit with ``nvtest.skip_exit_status`` or raise a ``nvtest.TestSkipped`` exception.

.. _stat-diffed:

diffed
------

A test diffs if it exits with a ``64`` exit code.

.. admonition:: Tip

   Don't explicitly exit with code ``64``.  Instead, exit with ``nvtest.diff_exit_status`` or raise a ``nvtest.TestDiffed`` exception.

.. _stat-failed:

failed
------

A test fails if it exits with any nonzero code not previously defined.

.. admonition:: Tip

   To explicitly mark a test as failed, exit with ``nvtest.fail_exit_status`` or raise a ``nvtest.TestFailed`` exception.

.. _stat-timeout:

timeout
-------

The test exceeded its allowed run time.

.. _stat-success:

success
-------

A test is considered successfully passed if it exits with a ``0`` exit code.

.. _stat-xfail:

xfail
-----

The test is marked as :ref:`expected to fail<directive-xfail>`

.. _stat-xdiff:

xdiff
-----

The test is marked as :ref:`expected to diff<directive-xdiff>`
