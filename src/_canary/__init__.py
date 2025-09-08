# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from .error import TestDiffed  # noqa: F401
from .error import TestFailed  # noqa: F401
from .error import TestSkipped  # noqa: F401
from .util.logging import setup_logging

setup_logging()
del setup_logging

# Constant that's True when file scanning, but False here.
FILE_SCANNING = False
