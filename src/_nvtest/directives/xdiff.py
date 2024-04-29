from typing import Optional

import _nvtest

from ..test.file import AbstractTestFile


def xdiff(*, when: Optional[str] = None):
    """The test is expected to diff.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       xdiff(when=None)

    Parameters
    ----------

    * ``when``: Restrict processing of the directive to this condition

    The ``when`` expression is limited to the following conditions:

    * ``testname``: Restrict processing of the directive to this test name
    * ``platforms``: Restrict processing of the directive to certain platform or
      platforms
    * ``options``: Restrict processing of the directive to command line ``-o`` options
    * ``parameters``: Restrict processing of the directive to certain parameter
      names and values

    """
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_xdiff(when=when)
