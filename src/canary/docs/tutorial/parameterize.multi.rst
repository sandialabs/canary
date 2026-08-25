.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-parameterize-multi:

Combining multiple parameter sets
=================================

If multiple ``parameterize`` directives are issued in the same test file, the cartesian product of parameters is performed:

.. literalinclude:: /examples/parameterize/parameterize3.pyt
    :language: python

.. doc-run::
   :before_script: ["ln -s $examples/parameterize/parameterize3.pyt ."]
   :script: ["canary describe parameterize3.pyt"]

Similarly,

.. literalinclude:: /examples/parameterize/parameterize4.pyt
    :language: python

results in the following 6 test cases:

.. doc-run::
   :before_script: ["ln -s $examples/parameterize/parameterize4.pyt ."]
   :script: ["canary describe parameterize4.pyt"]
