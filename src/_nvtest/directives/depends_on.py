from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def depends_on(
    arg: str,
    when: Optional[str] = None,
    expect: Optional[int] = None,
    result: Optional[str] = None,
):
    try:
        file: AbstractTestFile = _nvtest.__FILE_BEING_SCANNED__  # type: ignore
        file.m_depends_on(arg, when=when, result=result, expect=expect)
    except AttributeError:
        pass
