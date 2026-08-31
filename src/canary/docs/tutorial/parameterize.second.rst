.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-parameterize-second:

Multiple parameters
===================

A test can define multiple parameters by including multiple names and a corresponding table of values:

.. literalinclude:: /examples/parameterize/parameterize2.pyt
    :language: python

.. doc-run::
   :before_script: ["cp $examples/parameterize/parameterize2.pyt ."]
   :script: ["canary describe parameterize2.pyt"]

.. note::

    For ``len(names)`` must equal ``len(values[i])``.  E.g. ``len(['a', 'b']) == len((1, 2)) == len((5, 6))``.
