.. _tutorial-dependencies-result:

Controlling test execution based on dependency results
======================================================

By default, a test case will not run unless all of its dependencies complete successfully.  This behavior can be modified by passing the ``result`` argument to :func:`~canary.directives.depends_on`.

Example
-------

Run a test case only when its dependency fails:

.. literalinclude:: /examples/depends_on/result/depends_on_willfail.pyt
    :language: python

``depends_on_willfail`` will run only if the result of ``willfail`` is ``failed``:

.. command-output:: canary run ./depends_on/result
    :cwd: /examples
    :nocache:
    :anyreturncode:
    :setup: rm -rf TestResults


.. note::

   To execute a test regardless of the results of its dependencies, use ``result="*"``.
