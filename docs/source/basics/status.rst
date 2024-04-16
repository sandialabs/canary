.. _test-status:

Test statuses
=============

Tests can receive one of the following statuses:

* ``success``
* ``diff``
* ``skipped``
* ``fail``

success
-------

A test is considered successfully passed if it exits with a ``0`` exit code.

diff
----

A test diffs if it exits with a ``64`` exit code.

.. rubric:: Tip

Don't explicitly exit with code ``64``.  Instead, exit with ``nvtest.diff_exit_status`` or raise a ``nvtest.TestDiffed`` exception.

skipped
-------

A test will be skipped at runtime if it exits with a ``63`` exit code.

.. rubric:: Tip

Don't explicitly exit with code ``63``.  Instead, exit with ``nvtest.skip_exit_status`` or raise a ``nvtest.TestSkipped`` exception.

fail
----

A test fails if it exits with any nonzero code not previously defined.

.. rubric:: Tip

To explicitly mark a test as failed, exit with ``nvtest.fail_exit_status`` or raise a ``nvtest.TestFailed`` exception.
