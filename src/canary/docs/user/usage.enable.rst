.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _usage-enable:

Enabling/disabling tests
========================

Tests can be enabled and/or disabled using the :ref:`enable<directive-enable>` directive.  The following test will be run when the option ``-o enable`` is passed to ``canary run``, otherwise it will be skipped:

.. literalinclude:: /examples/enable/enable.pyt
    :language: python

.. doc-run::
   :before_script: [{"args": "cp -R $examples ."}]
   :script: [{"args": "canary run ./enable", "returns": 7, "cwd": "examples"}, {"args": "canary run -o enable ./enable", "cwd": "examples"}]
