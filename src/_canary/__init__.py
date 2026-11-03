# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from .core.error import TestDiffed as TestDiffed
from .core.error import TestFailed as TestFailed
from .core.error import TestSkipped as TestSkipped
from .util.logging import setup_logging

setup_logging()
del setup_logging
