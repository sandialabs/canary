from typing import Any
from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def set_attribute(*, when: Optional[str] = None, **attributes: Any) -> None:
    if isinstance(_nvtest.__FILE_BEING_SCANNED__, AbstractTestFile):
        file = _nvtest.__FILE_BEING_SCANNED__
        file.m_set_attribute(when=when, **attributes)
