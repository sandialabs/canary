from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def devices(*values: int, when: Optional[str] = None) -> None:
    try:
        file: AbstractTestFile = _nvtest.__FILE_BEING_SCANNED__  # type: ignore
        file.m_parameterize("ndevice", list(values), when=when)
    except AttributeError:
        pass
