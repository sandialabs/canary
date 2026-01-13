.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-enable:

Enabling/disabling tests
========================

Tests can be enabled and/or disabled using the :ref:`enable<directive-enable>` directive.  The following test will be run when the option ``-o enable`` is passed to ``canary run``, otherwise it will be skipped:

.. literalinclude:: /examples/enable/enable.pyt
    :language: python

.. command-output:: canary run -d TestResults.Enable ./enable
    :setup: rm -rf .canary TestResults.Enable
    :returncode: 7
    :cwd: /examples

.. command-output:: canary run -d TestResults.Enable -o enable ./enable
    :setup: rm -rf .canary TestResults.Enable
    :cwd: /examples
