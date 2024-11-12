.. _howto-centered-parameter-space:

Run a centered parameter space study
====================================

The centered parameter space computes parameter sets along multiple coordinate-based vectors, one per parameter, centered about the initial values.  The capability is modeled after the capability of the same name in `Dakota <https://www.sandia.gov/app/uploads/sites/241/2023/03/Users-6.13.0.pdf>`_.

The centered parameter space takes steps along each orthogonal dimension.  Each dimension is treated independently. The number of steps are taken in each direction, so that the total number of points in the parameter study is :math:`1+ 2\sum{n}`.

.. literalinclude:: /examples/centered_space/centered_space.pyt
    :language: python
    :lines: 1-19

will produce two test cases, one with ``a=1`` and another with ``a=4``, each executed in their own test directory:

.. command-output:: nvtest describe ./centered_space/centered_space.pyt
    :cwd: /examples
