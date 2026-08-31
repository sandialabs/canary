.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-enable:

Enabling/disabling tests
========================

Tests can be enabled and/or disabled using the :ref:`enable<directive-enable>` directive.  The following test will be run when the option ``-o enable`` is passed to ``canary run``, otherwise it will be skipped:

.. literalinclude:: /examples/enable/enable.pyt
    :language: python

.. doc-run::
   :before_script: [copy-examples]
   :script: ["canary run ./enable", "canary run -o enable ./enable"]
   :cwd: /examples
   :returncode: [7, 0]

