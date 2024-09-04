.. _howto-parameterize:

Parameterize tests
==================

A single test file can generate many test cases, each having different parameters, using the :ref:`parameterize <directive-parameterize>` directive.  The test file uses the parameter name[s] and value[s] to run variations of the test.  For example, the test script

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python

will produce two test cases, one with ``a=1`` and another with ``a=4``, each executed in their own test directory:

.. command-output:: nvtest describe parameterize/parameterize1.pyt
    :cwd: /examples

Multiple parameter names and their values can be defined:

.. literalinclude:: /examples/parameterize/parameterize2.pyt
    :language: python

which would result in the following two tests

.. command-output:: nvtest describe parameterize/parameterize2.pyt
    :cwd: /examples

If multiple ``parameterize`` directives are specified, the cartesian product of parameters is performed:

.. literalinclude:: /examples/parameterize/parameterize3.pyt
    :language: python

.. command-output:: nvtest describe parameterize/parameterize3.pyt
    :cwd: /examples

Similarly,

.. literalinclude:: /examples/parameterize/parameterize4.pyt
    :language: python

results in the following 6 test cases:

.. command-output:: nvtest describe parameterize/parameterize4.pyt
    :cwd: /examples

.. _np-ngpu-parameters:

np and ngpu parameters
----------------------

The ``np`` and ``ngpu`` parameters are interpreted by ``nvtest`` to be the number of processors and gpus, respectively, needed by the test case.  For compatiblity with ``vvtest``, ``ndevice`` is interpreted the same as ``ngpu``.

vvt parameter types
-------------------

In ``.vvt`` file types, parameters are read in by a json reader.  In general, numbers are parsed as numbers and anything that can't be cast to a number is left as a string.
