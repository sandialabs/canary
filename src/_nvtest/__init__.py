from typing import TYPE_CHECKING
from typing import Optional

from .error import TestDiffed  # noqa: F401
from .error import TestFailed  # noqa: F401
from .error import TestSkipped  # noqa: F401

if TYPE_CHECKING:
    from _nvtest.test.file import AbstractTestFile

# Constant that's True when file scanning, but False here.
FILE_SCANNING = False
__FILE_BEING_SCANNED__: Optional["AbstractTestFile"] = None
