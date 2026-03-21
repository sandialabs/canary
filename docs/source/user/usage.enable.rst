.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-enable:

Enabling/disabling tests
========================

Tests can be enabled and/or disabled using the :ref:`enable<directive-enable>` directive.  The following test will be run when the option ``-o enable`` is passed to ``canary run``, otherwise it will be skipped:

.. literalinclude:: /examples/enable/enable.pyt
    :language: python

.. command-output:: canary run ./enable
    :setup: rm -rf .canary TestResults
    :returncode: 7
    :cwd: /examples

.. command-output:: canary run -o enable ./enable
    :setup: rm -rf .canary TestResults
    :cwd: /examples


.. command-output:: rm -rf .canary TestResults
    :cwd: /examples
    :silent:
