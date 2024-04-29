.. _test-status:

Test statuses
=============

Tests can receive one of the following statuses:

* ``masked``
* ``created``
* ``ready``
* ``pending``
* ``running``
* ``cancelled``
* ``skipped``
* ``diffed``
* ``failed``
* ``timeout``
* ``success``

masked
------

The test was found in the search path but was filtered out of the list of tests to run.

created
-------

The test case object has been instantiated.

ready
-----

The test case is setup and ready to run.

pending
-------

The test case is waiting for one or more dependencies.

running
-------

The test case is currently running.

cancelled
---------

The test case was cancelled (usually by a keyboard interrupt).

skipped
-------

The test case was skipped due to a failed dependency or skipped at runtime by exiting a ``63`` exit code.

.. admonition:: Tip

   Don't explicitly exit with code ``63``.  Instead, exit with ``nvtest.skip_exit_status`` or raise a ``nvtest.TestSkipped`` exception.


diffed
------

A test diffs if it exits with a ``64`` exit code.

.. admonition:: Tip

   Don't explicitly exit with code ``64``.  Instead, exit with ``nvtest.diff_exit_status`` or raise a ``nvtest.TestDiffed`` exception.

failed
------

A test fails if it exits with any nonzero code not previously defined.

.. admonition:: Tip

   To explicitly mark a test as failed, exit with ``nvtest.fail_exit_status`` or raise a ``nvtest.TestFailed`` exception.

success
-------

A test is considered successfully passed if it exits with a ``0`` exit code.
