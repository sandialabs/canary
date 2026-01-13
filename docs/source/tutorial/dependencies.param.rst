.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-dependencies-param:

Establishing dependencies on specific test parameterizations
============================================================

Tests can depend on specific paramterizations of other tests.

Example
-------

The test ``lunch`` depends on ``breakfast``, but only when ``dish="spam"``:

.. literalinclude:: /examples/depends_on/parameter/breakfast.pyt
    :language: python

.. literalinclude:: /examples/depends_on/parameter/lunch.pyt
    :language: python

.. command-output:: canary run ./depends_on/parameter
    :cwd: /examples
    :nocache:
    :setup: rm -rf .canary TestResults
