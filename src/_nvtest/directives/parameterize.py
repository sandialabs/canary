from typing import Optional
from typing import Sequence
from typing import Union

import _nvtest

from ..test.testfile import AbstractTestFile
from . import enums


def parameterize(
    names: Union[str, Sequence[str]],
    values: list[Union[Sequence[object], object]],
    *,
    when: Optional[str] = None,
    type: enums.enums = enums.list_parameter_space,
) -> None:
    """Add new invocations to the test using the list of argvalues for the given
    argnames.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       parametrize(argnames, argvalues, when=None, type=None)


    ``.vvt``:

    .. code-block:: python

       #VVT: parametrize (options=...,platforms=...,testname=...) : argnames = argvalues

    Parameters
    ----------

    * ``argnames``: A comma-separated string denoting one or more argument
      names, or a list/tuple of argument strings.
    * ``argvalues``: If only one ``argname`` was specified, ``argvalues`` is a
      list of values.  If ``N`` ``argnames`` were specified, ``argvalues`` is a
      2D list of values where each column are the values for its respective
      ``argname``.
    * ``when``: Restrict processing of the directive to this condition
    * ``type``: (``.pyt`` only) Generate parameters using this type

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platform``: Restrict processing of the directive to certain platform or platforms
    * ``option``: Restrict processing of the directive to command line ``-o`` options

    Special argnames
    ----------------

    * `np`` interpreted to mean "number of processing cores".
      If the ``np`` parameter is not defined, the test is assumed to use 1
      processing core.
    * `ndevice`` interpreted to mean "number of devices" (gpus).
      If the ``ndevice`` parameter is not defined, the test is assumed to use 0
      devices.

    References
    ----------

    * :ref:`Parameterizing Tests <howto-parameterize>`

    Examples
    --------

    The following equivalent test specifications result in 4 test instantiations

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.parameterize("np", (4, 8, 12, 32))

    ``test1.vvt``:

    .. code-block:: python

       # test1
       #VVT: parameterize : np = 4 8 12 32

    .. code-block:: console

       4 test cases:
       ├── test1[np=4]
       ├── test1[np=8]
       ├── test1[np=12]
       ├── test1[np=32]

    ----

    ``argnames`` can be a list of parameters with associated ``argvalues``, e.g.

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.parameterize("a,b", ((1, 2), (3, 4), (5, 6)])

    ``test1.vvt``:

    .. code-block:: python

       # test1
       #VVT: parameterize : a,b = 1,2 3,4 5,6

    .. code-block:: console

       4 test cases:
       ├── test1[a=1,b=2]
       ├── test1[a=3,b=4]
       ├── test1[a=5,b=6]

    ----

    ``parameterize`` can be called multiple times.  When multiple parameterize
    directives are given, the Cartesian product of each is taken to form the set
    of parameters, e.g.

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.parameterize("a,b", [("a1", "b1"), ("a2", "b2")])
       nvtest.directives.parameterize("x", ["x1", "x2"])

    results in the following test invocations:

    .. code-block:: console

       4 test cases:
       ├── test1[a=a1,b=b1,x=x1]
       ├── test1[a=a1,b=b1,x=x2]
       ├── test1[a=a2,b=b2,x=x1]
       ├── test1[a=a2,b=b2,x=x2]

    """  # noqa: E501
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_parameterize(names, values, when=when, type=type)
