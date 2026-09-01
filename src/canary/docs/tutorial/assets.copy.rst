.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-assets-copy:

Copy files into the test working directory
==========================================

The :func:`canary.directives.copy` directive copies files into the test's working directory:

.. literalinclude:: /examples/copy_and_link/copy_and_link.pyt
    :language: python
    :emphasize-lines: 9, 14

Relative paths are assumed relative to the test file's source directory.
