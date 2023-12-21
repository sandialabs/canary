from typing import Optional
from typing import Union

import _nvtest

from ..test.testfile import AbstractTestFile


def timeout(arg: Union[str, float, int], *, when: Optional[str] = None):
    """Specify a timeout value for a test

    .. code-block:: python

       timeout(arg, when=None)

    .. code-block:: python

       # VVT: timeout (options=..., platforms=..., parameters=..., testname=...) : arg

    Parameters
    ----------

    * ``arg``: The time in seconds.  Natural language forms such as "20m", "1h
      20m", and HH:MM:SS such as "2:30:00" are also allowed and converted to
      seconds.
    * ``when``: Restrict processing of the directive to this condition

    Notes
    -----
    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    """
    try:
        file: AbstractTestFile = _nvtest.__FILE_BEING_SCANNED__  # type: ignore
        file.m_timeout(arg, when=when)
    except AttributeError:
        pass
