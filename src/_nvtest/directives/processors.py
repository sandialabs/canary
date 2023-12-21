from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def processors(*values: int, when: Optional[str] = None) -> None:
    """Run the test with this many processors

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       processors(*nprocs, when=None)


    ``.vvt``: NA

    Parameters
    ----------

    * ``nprocs``: List of processor counts
    * ``when``: Restrict processing of the directive to this condition

    Notes
    -----

    * ``processors(...)`` is equivalent to ``parameterize("np", ...)``

    * The ``when`` expression is limited to the following conditions:

      * ``testname``: Restrict processing of the directive to this test name
      * ``platform``: Restrict processing of the directive to certain platform or
        platforms
      * ``option``: Restrict processing of the directive to command line ``-o`` options

    Examples
    --------

    The following test specification result in 4 test instantiations

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.processors(4, 8, 12, 32)

    .. code-block:: console

       4 test cases:
       ├── test1[np=4]
       ├── test1[np=8]
       ├── test1[np=12]
       ├── test1[np=32]

    """
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_parameterize("np", list(values), when=when)
