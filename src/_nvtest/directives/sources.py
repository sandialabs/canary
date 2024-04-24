from typing import Optional

import _nvtest

from ..test.file import AbstractTestFile


def sources(*args: str, when: Optional[str] = None):
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_sources(*args, when=when)
