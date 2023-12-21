from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def sources(*args: str, when: Optional[str] = None):
    try:
        file: AbstractTestFile = _nvtest.__FILE_BEING_SCANNED__  # type: ignore
        file.m_sources(*args, when=when)
    except AttributeError:
        pass
