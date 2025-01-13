.. _tutorial-parameterize-second:

Multiple parameters
===================

A test can define multiple parameters by including multiple names and a corresponding table of values:

.. literalinclude:: /examples/parameterize/parameterize2.pyt
    :language: python

.. command-output:: nvtest describe parameterize/parameterize2.pyt
    :cwd: /examples

.. note::

    For ``len(names)`` must equal ``len(values[i])``.  E.g. ``len(['a', 'b']) == len((1, 2)) == len((5, 6))``.
