from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def devices(*values: int, when: Optional[str] = None) -> None:
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_parameterize("ndevice", list(values), when=when)
