from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def preload(arg: str, *, when: Optional[str] = None, source: bool = False):
    """Load shell shell script before test execution

    Usage
    -----

    ``.pyt``:

    .. code-block:: python

       preload(arg, *, when=None, source=False):

    ``.vvt``:

    .. code-block:: python

       # VVT: preload ([source]) : arg

    """
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_preload(arg, when=when, source=source)
