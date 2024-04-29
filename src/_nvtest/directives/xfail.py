from typing import Optional

import _nvtest

from ..test.file import AbstractTestFile


def xfail(*, code: int = -1, when: Optional[str] = None):
    """The test is expected to fail (return with a non-zero exit code).  If
    ``code > 0`` and the exit code is not ``code``, the test will be considered
    to have failed.

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       import nvtest
       nvtest.directives.xfail(code=-1, when=...)

    Parameters
    ----------

    * ``code``: The expected return code.  ``-1`` considers any non-zero return code to be a pass.
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
        file.m_xfail(code=code, when=when)
