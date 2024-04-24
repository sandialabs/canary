from typing import Any
from typing import Optional

import _nvtest

from ..test.file import AbstractTestFile


def set_attribute(*, when: Optional[str] = None, **attributes: Any) -> None:
    """Set an attribute on the test

    Usage
    -----

    ``.pyt``:

    .. code:: python

       set_attribute(*, when=None, **attributes)

    ``.vvt``: NA

    Parameters
    ----------

    * ``when``: Restrict processing of the directive to this condition
    * ``attributes``: ``attr:value`` pairs

    Examples
    --------

    .. code:: python

       import sys
       import nvtest
       nvtest.directives.set_attribute(program="program_name")

    will set the attribute ``program`` on the test case with value "program_name".

    """
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_set_attribute(when=when, **attributes)
