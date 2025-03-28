.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-xstatus:

Marking a test expected to diff or fail
=======================================

The :func:`canary.directives.xdiff` and :func:`canary.directives.xfail` directives can mark tests that you expect to diff or fail, respectively.  For example, the following test is expected to :ref:`diff <stat-diffed>`:

.. literalinclude:: /examples/xstatus/xdiff.pyt
    :language: python

.. command-output:: canary run ./xstatus/xdiff.pyt
    :cwd: /examples
    :setup: rm -rf TestResults

As you can see, the test status was set to :ref:`stat-xdiff` which is considered a successful outcome.

However, if a test that is marked to :ref:`diff <stat-diffed>` or :ref:`fail <stat-failed>` and does not, it will be considered a failure:

.. literalinclude:: /examples/xstatus/xfail-fail.pyt
    :language: python

.. command-output:: canary run ./xstatus/xfail-fail.pyt
    :cwd: /examples
    :returncode: 4
    :setup: rm -rf TestResults

Specifying a nonzero exit code
------------------------------

If a nonzero exit code is expected, use ``canary.directives.xfail(code)``, where ``code`` is the expected exit code.  Any other exit code other than ``code`` will be considered a failure.

.. literalinclude:: /examples/xstatus/xfail-code.pyt
    :language: python

.. command-output:: canary run ./xstatus/xfail-code.pyt
    :cwd: /examples
    :setup: rm -rf TestResults
