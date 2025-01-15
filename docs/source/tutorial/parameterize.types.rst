.. _tutorial-parameterize-types:

Types of parameterizations
==========================

:func:`~canary.directives.parameterize` takes an optional ``type`` argument, allowing parameters to be generated in different ways from the input ``values``.  Three ``type``\ s are recoginized:

* :ref:`list_parameter_space <tutorial-list-parameter-space>` (default)
* :ref:`centered_parameter_space <tutorial-centered-parameter-space>`
* :ref:`random_parameter_space <tutorial-random-parameter-space>`

.. _tutorial-list-parameter-space:

type=canary.list_parameter_space
--------------------------------

.. code-block:: python

    def parameterize(
        names: str | tuple[str],
        values: Iterable[Iterable[str | float | int]],
        when: dict | str,
        type: canary.enums = canary.list_parameter_space
    )

The ``list_parameter_space`` reads lists of parameter values as defined by the user.  ``names`` is
a comma-separated list of names, or tuple of names.  ``values`` is the list of the associated
values such that ``len(values[i])`` are the parameter values for the ``i``'th generated test case.
Consequently, ``len(names) == len(values[i])`` for all ``i``.

This is the default parameterization shown in :ref:`tutorial-parameterize-first` and :ref:`tutorial-parameterize-multi`.

.. _tutorial-centered-parameter-space:

type=canary.centered_parameter_space
------------------------------------

.. code-block:: python

    def parameterize(
        names: str | tuple[str],
        values: Iterable[Iterable[str | float | int]],
        samples: int = 10,
        when: dict | str,
        type: canary.enums = canary.centered_parameter_space
    )

The ``centered_parameter_space`` type computes parameter sets along multiple coordinate-based
vectors, one per parameter, centered about the initial values.  ``names`` is a tuple or
comma-separated string of parameter names and ``values`` is a list of tuples where ``values[i] =
(initial_value, step_size, num_steps)`` define the initial value, step size, and number of steps
for the ``i``\ th parameter.

The capability is modeled after the capability of the same name in
`Dakota <https://www.sandia.gov/app/uploads/sites/241/2023/03/Users-6.13.0.pdf>`_.

The centered parameter space takes steps along each orthogonal dimension.  Each dimension is treated independently. The number of steps are taken in each direction, so that the total number of points in the parameter study is :math:`1+ 2\sum{n}`.

Example
~~~~~~~

.. literalinclude:: /examples/centered_space/centered_space.pyt
    :language: python
    :lines: 1-19

will produce two test cases, one with ``a=1`` and another with ``a=4``, each executed in their own test directory:

.. command-output:: canary describe ./centered_space/centered_space.pyt
    :cwd: /examples

.. _tutorial-random-parameter-space:

type=random_parameter_space
---------------------------

.. code-block:: python

    def parameterize(
        names: str | tuple[str],
        values: Iterable[Iterable[str | float | int]],
        samples: int = 10,
        seed: float = 1234.,
        when: dict | str,
        type: canary.enums = canary.random_parameter_space
    )

The ``random_parameter_space`` type computes random parameter values. ``names`` is a tuple or
comma-separated string of parameter names and ``values`` is a list of tuples where ``values[i] =
(start, stop)`` define the range from which ``samples`` random elements are taken.

Example
~~~~~~~

.. literalinclude:: /examples/random_space/random_space.pyt
    :language: python

will produce four test cases, each with ``a`` and ``b`` being chosen randomly in the range ``0:5`` and ``6:10``, respectively:

.. command-output:: canary describe ./random_space/random_space.pyt
    :cwd: /examples
