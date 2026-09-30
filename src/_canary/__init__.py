# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from .core.error import TestDiffed  # noqa: F401
from .core.error import TestFailed  # noqa: F401
from .core.error import TestSkipped  # noqa: F401
from .util.logging import setup_logging

setup_logging()
del setup_logging
