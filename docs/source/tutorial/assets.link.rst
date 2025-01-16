.. _tutorial-assets-link:

Link files into the test working directory
==========================================

The :func:`canary.directives.link` directive links files into the test's working directory:

.. literalinclude:: /examples/copy_and_link/copy_and_link.pyt
    :language: python
    :emphasize-lines: 6, 11

Relative paths are assumed relative to the test file's source directory.
