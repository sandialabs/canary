.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _basics-copy-and-link:

Copying and linking resource files into the test execution directory
====================================================================

Resources needed by tests can be copied and linked from their source locations to the execution directory with the :func:`canary.directives.copy` and :func:`canary.directives.link` directives, respectively, as shown in the following example:

.. literalinclude:: /examples/copy_and_link/copy_and_link.pyt
    :language: python

.. doc-run::
   :before_script: [{"args": "cp -R $examples/copy_and_link ."}]
   :script: [{"args": "canary run ./copy_and_link/", "ellipsis": 0}, {"args": "ls -l $(canary location copy_and_link)/*.txt"}]
