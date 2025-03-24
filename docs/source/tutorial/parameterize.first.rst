.. _tutorial-parameterize-first:

Getting started with parameterization
=====================================

In the most simple case, a single parameter is defined, as demonstrated in the example ``paramterize/parameterize1.pyt``:

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python

The test file generates two test cases with parameters ``a=1`` and ``a=4``, respectively:

.. command-output:: canary describe parameterize/parameterize1.pyt
    :cwd: /examples

When the test file is run, each case is executed in its own uniquely named directory:

.. command-output:: canary run parameterize/parameterize1.pyt
   :cwd: /examples
   :nocache:
   :setup: rm -rf TestResults

.. command-output:: ls -F TestResults/
   :cwd: /examples
   :nocache:

Test directories are generally named ``$family.$param_1=$value_1...$param_n=$value_n``, where ``family`` is (usually) the basename of the test file.
