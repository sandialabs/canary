from typing import Any
from typing import Optional

import _nvtest

from ..test.testfile import AbstractTestFile


def set_attribute(*, when: Optional[str] = None, **attributes: Any) -> None:
    try:
        file: AbstractTestFile = _nvtest.__FILE_BEING_SCANNED__  # type: ignore
        file.m_set_attribute(when=when, **attributes)
    except AttributeError:
        pass
