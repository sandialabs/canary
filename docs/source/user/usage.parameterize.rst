.. _usage-parameterize:

Parameterizing tests
====================

A single test file can generate many test cases, each having different parameters, using the :ref:`parameterize <directive-parameterize>` directive.  The test file uses the parameter name[s] and value[s] to run variations of the test.  For example

.. code-block:: python

    canary.directives.parameterize("odd,even", [(1, 2), (3, 4)])

instructs ``canary`` to create two test instances with parameters ``odd=1`` and ``even=2`` in the first, and parameters ``odd=3`` and ``even=4`` in the second.

.. _cpus-gpus-parameters:

Special parameter names
-----------------------

The ``cpus`` and ``gpus`` parameters are interpreted by ``canary`` to be the number of cpus and gpus, respectively, needed by the test case.

.. admonition:: vvtest compatiblity

    The ``np`` and ``ndevice`` parameters are taken to be synonyms for ``cpus`` and ``gpus``, respectively.


The type argument
-----------------

``parameterize`` takes an optional argument ``type``, allowing parameters to be generated in different ways from the input ``values``.  Three ``type``\ s are recoginized:

* :ref:`list_parameter_space <list-parameter-space>` (default)
* :ref:`centered_parameter_space <centered-parameter-space>`
* :ref:`random_parameter_space <random-parameter-space>`

.. _list-parameter-space:

type=canary.list_parameter_space
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def parameterize(
        names: str | tuple[str],
        values: Iterable[Iterable[str | float | int]],
        when: dict | str,
        type: canary.enums = canary.list_parameter_space
    )

The ``list_parameter_space`` reads lists of parameter values as defined by the user.  ``names`` is a comma-separated list of names, or tuple of names.  ``values`` is the list of the associated values such that ``len(values[i])`` are the parameter values for the ``i``'th generated test case.  Consequently, ``len(names) == len(values[i])`` for all ``i``.  For example,

.. literalinclude:: /examples/parameterize/parameterize1.pyt
    :language: python

will produce two test cases, one with ``a=1`` and another with ``a=4``, each executed in their own test directory:

.. command-output:: canary describe parameterize/parameterize1.pyt
    :cwd: /examples

Multiple parameter names and their values can be defined:

.. literalinclude:: /examples/parameterize/parameterize2.pyt
    :language: python

which would result in the following two tests

.. command-output:: canary describe parameterize/parameterize2.pyt
    :cwd: /examples

.. _centered-parameter-space:

type=canary.centered_parameter_space
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def parameterize(
        names: str | tuple[str],
        values: Iterable[Iterable[str | float | int]],
        samples: int = 10,
        when: dict | str,
        type: canary.enums = canary.centered_parameter_space
    )

The ``centered_parameter_space`` type computes parameter sets along multiple coordinate-based vectors, one per parameter, centered about the initial values.  ``names`` is a tuple or comma-separated string of parameter names and ``values`` is a list of tuples where ``values[i] = (initial_value, step_size, num_steps)`` define the initial value, step size, and number of steps for the ``i``\ th parameter.

The capability is modeled after the capability of the same name in `Dakota <https://www.sandia.gov/app/uploads/sites/241/2023/03/Users-6.13.0.pdf>`_.

The centered parameter space takes steps along each orthogonal dimension.  Each dimension is treated independently. The number of steps are taken in each direction, so that the total number of points in the parameter study is :math:`1+ 2\sum{n}`.

Example
.......

.. literalinclude:: /examples/centered_space/centered_space.pyt
    :language: python
    :lines: 1-19

will produce two test cases, one with ``a=1`` and another with ``a=4``, each executed in their own test directory:

.. command-output:: canary describe ./centered_space/centered_space.pyt
    :cwd: /examples

.. _random-parameter-space:

type=random_parameter_space
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    def parameterize(
        names: str | tuple[str],
        values: Iterable[Iterable[str | float | int]],
        samples: int = 10,
        when: dict | str,
        type: canary.enums = canary.random_parameter_space
    )

The ``random_parameter_space`` type computes random parameter values. ``names`` is a tuple or comma-separated string of parameter names and ``values`` is a list of tuples where ``values[i] = (start, stop)`` define the range from which ``samples`` random elements are taken.

Example
.......

.. literalinclude:: /examples/random_space/random_space.pyt
    :language: python

will produce four test cases, each with ``a`` and ``b`` being chosen randomly in the range ``0:5`` and ``6:10``, respectively:

.. command-output:: canary describe ./random_space/random_space.pyt
    :cwd: /examples

Combining multiple parameter sets
---------------------------------

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
