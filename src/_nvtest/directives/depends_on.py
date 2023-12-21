from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def depends_on(
    arg: str,
    when: Optional[str] = None,
    expect: Optional[int] = None,
    result: Optional[str] = None,
):
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_depends_on(arg, when=when, result=result, expect=expect)
