# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Backward-compatible re-export shim.

The canonical location of these symbols is now ``canary_pyt.paramset``.
This module re-exports everything from there so that existing code that
imports from ``_canary.paramset`` continues to work without modification.
"""

import warnings

warnings.warn(
    "_canary.paramset is deprecated; import from canary_pyt.paramset instead.",
    DeprecationWarning,
    stacklevel=2,
)

from canary_pyt.paramset import ParameterSet  # noqa: F401, E402
from canary_pyt.paramset import append_if_unique  # noqa: F401, E402
from canary_pyt.paramset import is_scalar  # noqa: F401, E402
from canary_pyt.paramset import random_range  # noqa: F401, E402
from canary_pyt.paramset import transpose  # noqa: F401, E402

__all__ = ["ParameterSet", "append_if_unique", "is_scalar", "random_range", "transpose"]
