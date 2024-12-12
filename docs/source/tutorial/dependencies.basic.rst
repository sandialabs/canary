.. _tutorial-dependencies-basic:

Basic test dependencies
=======================

The :func:`~nvtest.directives.depends_on` directive designates one test as dependent on another.  Dependent tests will not run until all of its dependencies run to completion. When it is run, it can query the properties of its dependencies by the ``instance.dependencies`` attribute.

Example
-------

.. literalinclude:: /examples/depends_on/basic/depends_on_a.pyt
    :language: python

``depends_on_a`` will not run until after ``a`` runs:

.. command-output:: nvtest run ./depends_on/basic
    :cwd: /examples
    :nocache:
    :extraargs: -w
