from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def devices(*ndevices: int, when: Optional[str] = None) -> None:
    """Run the test with this many devices

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       devices(*ndevices, when=None)


    ``.vvt``: NA

    Parameters
    ----------

    * ``ndevices``: List of device counts counts
    * ``when``: Restrict processing of the directive to this condition

    Notes
    -----
    * ``devices(...)`` is equivalent to ``parameterize("ndevice", ...)``

    * The ``when`` expression is limited to the following conditions:

      * ``testname``: Restrict processing of the directive to this test name
      * ``platform``: Restrict processing of the directive to certain platform or
        platforms
      * ``option``: Restrict processing of the directive to command line ``-o`` options

    Examples
    --------

    The following equivalent test specifications result in 4 test instantiations

    ``test1.pyt``:

    .. code-block:: python

       # test1
       nvtest.directives.devices(1, 2)

    .. code-block:: console

       2 test cases:
       ├── test1[ndevies=1]
       ├── test1[ndevices=2]

    """
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_parameterize("ndevice", list(ndevices), when=when)
