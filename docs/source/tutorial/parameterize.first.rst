.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-parameterize-first:

Getting started with parameterization
=====================================

In the most simple case, a single parameter is defined, as demonstrated in the example ``paramterize/parameterize1.pyt``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python

The test file generates two test cases with parameters ``a=1`` and ``a=4``, respectively:

.. doc-run::
   :before_script: [link-examples]
   :script: [canary describe parameterize/parameterize1.pyt]
   :cwd: /examples

When the test file is run, each case is executed in its own uniquely named directory:

.. doc-run::
   :before_script: [link-examples]
   :script: [canary run parameterize/parameterize1.pyt, ls -F TestResults]
   :cwd: /examples

Test directories are generally named ``$family.$param_1=$value_1...$param_n=$value_n``, where ``family`` is (usually) the basename of the test file.
