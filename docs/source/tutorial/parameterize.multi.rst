.. _tutorial-parameterize-multi:

Combining multiple parameter sets
=================================

If multiple ``parameterize`` directives are issued in the same test file, the cartesian product of parameters is performed:

.. literalinclude:: /examples/parameterize/parameterize3.pyt
    :language: python

.. command-output:: canary describe parameterize/parameterize3.pyt
    :cwd: /examples

Similarly,

.. literalinclude:: /examples/parameterize/parameterize4.pyt
    :language: python

results in the following 6 test cases:

.. command-output:: canary describe parameterize/parameterize4.pyt
    :cwd: /examples
