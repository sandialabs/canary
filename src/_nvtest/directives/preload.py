from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def preload(self, arg: str, *, when: Optional[str] = None, source: bool = False):
    try:
        file: AbstractTestFile = _nvtest.__FILE_BEING_SCANNED__  # type: ignore
        file.m_preload(arg, when=when, source=source)
    except AttributeError:
        pass
