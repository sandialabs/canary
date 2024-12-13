.. _tutorial-assets-copy:

Copy files into the test working directory
==========================================

The :func:`nvtest.directives.copy` directive copies files into the test's working directory:

.. literalinclude:: /examples/copy_and_link/copy_and_link.pyt
    :language: python
    :emphasize-lines: 5, 10

Relative paths are assumed relative to the test file's source directory.
