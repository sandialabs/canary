.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-dependencies-basic:

Basic test dependencies
=======================

The :func:`~canary.directives.depends_on` directive designates one test case as dependent on another.  Dependent test cases will not run until all of its dependencies run to completion. When the test case is run, it can query the properties of its dependencies by the ``instance.dependencies`` attribute.

Example
-------

.. literalinclude:: /examples/depends_on/basic/depends_on_a.pyt
    :language: python

``depends_on_a`` will not run until after ``a`` runs:

.. command-output:: canary run ./depends_on/basic
    :cwd: /examples
    :nocache:
    :setup: rm -rf .canary TestResults
